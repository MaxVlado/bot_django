import pytest

# подключаем наш плагин
pytest_plugins = ["tests.scenario_cov"]

@pytest.fixture(autouse=True)
def wfp_signature_off(settings):
    # В тестах можно отключать строгую проверку подписи
    settings.WAYFORPAY_VERIFY_SIGNATURE = False
