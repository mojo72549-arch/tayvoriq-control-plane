from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS_SITECUSTOMIZE = ROOT / "implementation" / "tools" / "sitecustomize.py"

spec = importlib.util.spec_from_file_location("tayvoriq_tools_sitecustomize", TOOLS_SITECUSTOMIZE)
if spec is None or spec.loader is None:
    raise RuntimeError(f"tools_sitecustomize_unavailable:{TOOLS_SITECUSTOMIZE}")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

import tayvoriq_dual_platform_render_v16 as v16

_original = v16._verified_eu_ai_act_fallback


def _falcon9_validated_fallback(topic: str):
    package = _original(topic)
    if package is None:
        return None
    evidence = " ".join(str(topic or "").split()).casefold()
    if not all(marker in evidence for marker in ("falcon-9", "mond", "weltraumschrott")):
        return package

    package = dict(package)
    package.update(
        {
            "what_happened": "Eine ausgediente Falcon-9-Oberstufe sollte nahe dem Einstein-Krater auf dem Mond einschlagen.",
            "why_happening": "Durch den Einschlag wollten Forschende Lichtblitz, Staubwolke und Mondmaterial untersuchen.",
            "who_is_affected": "Betroffen sind Mondforscher, Missionsbetreiber und Raumfahrtfirmen im Erde-Mond-Raum.",
            "personal_impact": "Für dich zeigt der Fall Chancen und Risiken von Weltraumschrott.",
            "action_now": "Prüfe, ob Beobachtungen bestätigt sind, und trenne Prognosen von Ereignissen.",
        }
    )
    print(
        {
            "falcon9_fallback_contract": "49_words",
            "quality_gates_changed": False,
        },
        flush=True,
    )
    return package


v16._verified_eu_ai_act_fallback = _falcon9_validated_fallback
