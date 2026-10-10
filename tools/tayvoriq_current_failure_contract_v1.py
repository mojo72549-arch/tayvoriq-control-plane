"""Bind the current producer failure, never an earlier checkpoint finding."""
from __future__ import annotations

if __package__:
    from .tayvoriq_recovery_policy_v1 import (
        EDITORIAL_CODEFIX_PATTERNS, SEMANTIC_CODEFIX_PATTERNS, _matches, runtime_log_text,
        LOCAL_VOICE_RETRY_PATTERNS, LOCAL_VISUAL_RETRY_PATTERNS,
    )
else:
    from tayvoriq_recovery_policy_v1 import (
        EDITORIAL_CODEFIX_PATTERNS, SEMANTIC_CODEFIX_PATTERNS, _matches, runtime_log_text,
        LOCAL_VOICE_RETRY_PATTERNS, LOCAL_VISUAL_RETRY_PATTERNS,
    )


def bind_current_failure(payload, console, *, run_id, run_attempt, request_id):
    result = dict(payload)
    result.update(run_id=int(run_id), run_attempt=int(run_attempt), request_id=request_id)
    # A console emitted by this controller invocation may terminate before it
    # refreshes report.json. Explicit runtime contract errors supersede that old
    # report's local repair targets. Echoed workflow source is never proof.
    state, detail = "", ""
    for line in runtime_log_text(console).splitlines():
        if _matches(line, EDITORIAL_CODEFIX_PATTERNS):
            state = "EDITORIAL_VALIDATOR_CODEFIX_REQUIRED"
            detail = line
        elif _matches(line, SEMANTIC_CODEFIX_PATTERNS):
            state = "SEMANTIC_CODEFIX_REQUIRED"
            detail = line
        elif _matches(line, LOCAL_VOICE_RETRY_PATTERNS + LOCAL_VISUAL_RETRY_PATTERNS):
            # A later local failure owns the terminal result if the earlier
            # editorial defect was repaired within this same controller attempt.
            state, detail = "", ""
    if state:
        result.update(state=state, failure_class="DETERMINISTIC_CODE",
                      repair_target_stages=[], master_reusable=False,
                      failure_detail=detail[-1000:])
    return result
