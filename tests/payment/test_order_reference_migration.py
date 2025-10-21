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
def test_parse_order_reference_invalid_format_without_prefix():
    """
    Неверный формат без префикса ORDER_ должен вызывать ошибку.
    Формат: 5_6708861351_1_1700000000 (без ORDER_)
    """
    api = WayForPayAPI()
    ref = "5_6708861351_1_1700000000"
    
    with pytest.raises(ValueError, match="must start with ORDER_"):
        api.parse_order_reference(ref)


@covers("S18.1")
def test_parse_order_reference_valid_new_format():
    """
    Правильный новый формат: ORDER_timestamp+rand_user_plan должен парситься корректно.
    """
    api = WayForPayAPI()
    ref = "ORDER_1700000000abc_6708861351_1"
    
    user_id, plan_id, timestamp = api.parse_order_reference(ref)
    
    assert user_id == 6708861351
    assert plan_id == 1
    assert timestamp == 1700000000