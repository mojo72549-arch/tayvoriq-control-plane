from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE = Path("tools/tayvoriq_codefix_orphan_reconcile_v1.py")
SPEC = importlib.util.spec_from_file_location("tayvoriq_codefix_orphan_reconcile_v1", MODULE)
assert SPEC and SPEC.loader
orphan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(orphan)


def test_source_repair_requests_are_telegram_bound_and_auto_repairable() -> None:
    request = {
        "source": "telegram_trend_approval_source_repair",
        "source_context": {},
    }

    assert orphan._telegram_bound(request) is True
    assert orphan._auto_repair(request) is True


def test_nontelegram_source_is_not_implicitly_auto_repairable() -> None:
    request = {
        "source": "scheduled_research",
        "source_context": {},
    }

    assert orphan._telegram_bound(request) is False
    assert orphan._auto_repair(request) is False
