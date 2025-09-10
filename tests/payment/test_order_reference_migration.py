# tests/test_order_reference_migration.py
import pytest
from tests.scenario_cov import covers

# стараемся быть совместимыми с разными путями пакета
import importlib
mod = None
for p in ("wayforpay.api", "payments.wayforpay.api"):
    try:
        mod = importlib.import_module(p)
        break
    except ImportError:
        continue
assert mod is not None, "WayForPayAPI module not found"
WayForPayAPI = getattr(mod, "WayForPayAPI")


@covers("S18.1")
def test_parse_order_reference_old_format():
    """
    Старый формат: bot_user_plan_ts — должен корректно распарситься.
    """
    api = WayForPayAPI()
    ref = "5_6708861351_1_1700000000"
    bot_id, user_id, plan_id, ts = api.parse_order_reference(ref)
    assert (bot_id, user_id, plan_id, ts) == (5, 6708861351, 1, 1700000000)


@covers("S18.1")
def test_parse_order_reference_new_format_with_suffix():
    """
    Новый формат: bot_user_plan_tsMs_rand6 — должны игнорировать хвост и парсить первые 4 части.
    """
    api = WayForPayAPI()
    ref = "5_6708861351_1_1700000000123_abcdef"
    bot_id, user_id, plan_id, ts = api.parse_order_reference(ref)
    assert (bot_id, user_id, plan_id, ts) == (5, 6708861351, 1, 1700000000123)
