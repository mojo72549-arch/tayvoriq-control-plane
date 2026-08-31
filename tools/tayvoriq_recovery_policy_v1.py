from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


EXTERNAL_PATTERNS = (
    r"external_auth_blocker",
    r"external_action_required",
    r"missing (?:required )?secret",
    r"401 client error",
    r"unauthorized",
    r"credentials?[^\n]*(?:missing|invalid|expired)",
    r"billing (?:account|status)[^\n]*(?:disabled|suspended|blocked)",
    r"spending limit (?:reached|exceeded)",
    r"payment required",
    r"permission denied",
)

DUPLICATE_PATTERNS = (
    r"duplicate_content_blocked",
    r"dublette verhindert",
    r"duplicate blocked",
)

PUBLISHABLE_RETRY_PATTERNS = (
    r"checkpoint handoff:\s*state=publishable_output_retry_required",
    r"recovery=publishable_output_retry_required",
    r'"state"\s*:\s*"publishable_output_retry_required"',
)

# These messages mean the bounded in-run repair mechanism itself has already
# tried the safe local path and still cannot converge. A fresh generation with
# unchanged code is not a meaningful recovery; keep the exact request armed for
# verified codefix continuity instead of opening a dead circuit.
LOCAL_REPAIR_CODEFIX_PATTERNS = (
    r"bounded localized repair exhausted",
    r"localized checkpoint repair failed safely",
    r"checkpoint repair completed but .* residual blockers",
    r"fresh strict audit after localized repair still contains",
    r"visual checkpoint topic-aware repair failed",
    r"voice checkpoint v5 natural narrator repair failed",
)

# A terminal controller handoff is authoritative over provider-level noise that
# happened earlier in the same run. In particular, CODE_REPAIR_REQUIRED must not
# be downgraded to a transient same-run retry just because a provider logged a
# timeout/circuit-open message before the controller exhausted its safe repair
# path. This is what makes deterministic codefix continuity actually reachable.
TERMINAL_CODE_REPAIR_PATTERNS = (
    r"controller handoff:\s*state=code_repair_required\b",
    r"production is not publishable:\s*controller=code_repair_required/",
    r'"state"\s*:\s*"code_repair_required"',
    r"tayvoriq_autonomous_recovery:\s*no safe patch passed validation",
)

TRANSIENT_PATTERNS = (
    r"\b429\b",
    r"too many requests",
    r"timed out",
    r"timeout",
    r"connection reset",
    r"temporary failure",
    r"temporarily unavailable",
    r"\b502\b",
    r"\b503\b",
    r"\b504\b",
    r"transient_audio_failure",
    r"circuit already open",
)

DETERMINISTIC_PREFLIGHT_PATTERNS = (
    r"\bpreflight_failed\b",
    r"production blocked before render:\s*preflight outcome=failure",
    r"=+ failures =+",
    r"failed tests/[^\s]+",
    r"pytest[^\n]*returncode[^\n]*1",
)


@dataclass(frozen=True)
class RecoveryDecision:
    mode: str
    state: str
    retry_allowed: bool
    retry_kind: str
    current_generation: int
    next_generation: int | None
    max_generations: int
    failure_signature: str
    reason: str


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _stable_signature(state: str, logs: str) -> str:
    failed_tests = sorted(set(re.findall(r"FAILED\s+(tests/[^\s:]+(?:::[^\s]+)?)", logs, flags=re.IGNORECASE)))
    salient = "|".join(item.casefold() for item in failed_tests[:8]) or state.casefold()
    return hashlib.sha256(f"{state}|{salient}".encode("utf-8")).hexdigest()[:20]


def classify_failure(
    logs: str,
    *,
    run_attempt: int = 1,
    recovery_generation: int = 0,
    max_generations: int = 4,
    owner_found: bool = True,
    owner_current: bool = True,
    exact_request_retry: bool = False,
) -> RecoveryDecision:
    text = str(logs or "")
    lowered = text.casefold()
    attempt = max(1, int(run_attempt or 1))
    generation = max(0, int(recovery_generation or 0))
    maximum = max(1, int(max_generations or 1))

    if not owner_found:
        state = "RECOVERY_OWNER_MISSING"
        return RecoveryDecision("unowned", state, False, "none", generation, None, maximum, _stable_signature(state, text), "No durable request owns the failed run.")

    if not owner_current:
        state = "SUPERSEDED_RECOVERY_EVENT"
        return RecoveryDecision("stale", state, False, "none", generation, None, maximum, _stable_signature(state, text), "A newer run already owns the request.")

    if _matches(lowered, LOCAL_REPAIR_CODEFIX_PATTERNS):
        state = "LOCAL_REPAIR_CODEFIX_REQUIRED"
        return RecoveryDecision(
            "deterministic",
            state,
            False,
            "verified-codefix-replay",
            generation,
            generation,
            maximum,
            _stable_signature(state, text),
            "Bounded local repair already ran and the strict audit still failed; keep the exact request armed for a verified codefix replay in the same recovery generation.",
        )

    if _matches(lowered, PUBLISHABLE_RETRY_PATTERNS):
        if generation >= maximum:
            state = "PUBLISHABLE_CODEFIX_REQUIRED"
            return RecoveryDecision(
                "deterministic",
                state,
                False,
                "verified-codefix-replay",
                generation,
                generation,
                maximum,
                _stable_signature(state, text),
                "The publishability gate is still failing at the generation ceiling; preserve the exact request and continue only after a verified relevant code revision.",
            )
        state = "REQUEST_BOUND_RECOVERY_REQUIRED"
        return RecoveryDecision("fresh", state, True, "fresh-run", generation, generation + 1, maximum, _stable_signature(state, text), "The final publishability gate requires a bounded request-bound recovery generation.")

    if _matches(lowered, EXTERNAL_PATTERNS):
        state = "EXTERNAL_ACTION_REQUIRED"
        return RecoveryDecision("external", state, False, "none", generation, None, maximum, _stable_signature(state, text), "Credentials, billing or permissions require external action.")

    if _matches(lowered, DETERMINISTIC_PREFLIGHT_PATTERNS):
        state = "DETERMINISTIC_PREFLIGHT_FAILURE"
        return RecoveryDecision("deterministic", state, False, "none", generation, None, maximum, _stable_signature(state, text), "Repository tests or the deterministic preflight failed; an identical retry cannot repair code.")

    if _matches(lowered, TERMINAL_CODE_REPAIR_PATTERNS):
        state = "CODE_REPAIR_REQUIRED"
        return RecoveryDecision(
            "deterministic",
            state,
            False,
            "verified-codefix-replay",
            generation,
            generation,
            maximum,
            _stable_signature(state, text),
            "The controller exhausted its bounded safe repair path and handed off CODE_REPAIR_REQUIRED; preserve the exact request for verified codefix replay instead of treating earlier provider noise as transient.",
        )

    if _matches(lowered, DUPLICATE_PATTERNS):
        if exact_request_retry:
            state = "DUPLICATE_RETRY_CONTRACT_BROKEN"
            return RecoveryDecision("deterministic", state, False, "none", generation, None, maximum, _stable_signature(state, text), "The exact approved request was incorrectly treated as a duplicate during recovery.")
        state = "DUPLICATE_CONTENT_BLOCKED"
        return RecoveryDecision("duplicate", state, False, "none", generation, None, maximum, _stable_signature(state, text), "The duplicate gate intentionally blocked this content.")

    if attempt < 3 and _matches(lowered, TRANSIENT_PATTERNS):
        state = "SAME_RUN_TRANSIENT_RECOVERY"
        return RecoveryDecision("rerun", state, True, "same-run", generation, generation, maximum, _stable_signature(state, text), "The failure is transient; retry the same run without creating a new generation.")

    if generation >= maximum:
        state = "RECOVERY_CODEFIX_REQUIRED"
        return RecoveryDecision(
            "deterministic",
            state,
            False,
            "verified-codefix-replay",
            generation,
            generation,
            maximum,
            _stable_signature(state, text),
            "The owned internal request reached the fresh-generation ceiling. Preserve it and resume only after a verified relevant code revision instead of opening a dead recovery circuit.",
        )

    state = "REQUEST_BOUND_RECOVERY_REQUIRED"
    return RecoveryDecision("fresh", state, True, "fresh-run", generation, generation + 1, maximum, _stable_signature(state, text), "A bounded request-bound recovery generation may be started.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--logs-file", required=True)
    parser.add_argument("--run-attempt", type=int, default=1)
    parser.add_argument("--recovery-generation", type=int, default=0)
    parser.add_argument("--max-generations", type=int, default=4)
    parser.add_argument("--owner-found", choices=("true", "false"), default="true")
    parser.add_argument("--owner-current", choices=("true", "false"), default="true")
    parser.add_argument("--exact-request-retry", choices=("true", "false"), default="false")
    parser.add_argument("--output-json")
    args = parser.parse_args()

    logs = Path(args.logs_file).read_text(encoding="utf-8", errors="replace") if Path(args.logs_file).is_file() else ""
    decision = classify_failure(
        logs,
        run_attempt=args.run_attempt,
        recovery_generation=args.recovery_generation,
        max_generations=args.max_generations,
        owner_found=args.owner_found == "true",
        owner_current=args.owner_current == "true",
        exact_request_retry=args.exact_request_retry == "true",
    )
    payload = asdict(decision)
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
