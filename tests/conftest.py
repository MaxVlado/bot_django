import pytest
from pathlib import Path
import tempfile
import shutil

# подключаем наш плагин
pytest_plugins = ["tests.scenario_cov"]

@pytest.fixture(autouse=True)
def wfp_signature_off(settings):
    # В тестах можно отключать строгую проверку подписи
    settings.WAYFORPAY_VERIFY_SIGNATURE = False

@pytest.fixture(autouse=True)
def use_temp_media_root(settings):
    """Используем временную директорию для MEDIA_ROOT в тестах"""
    # Создаем временную директорию
    temp_dir = Path(tempfile.mkdtemp())
    
    # Переопределяем MEDIA_ROOT
    settings.MEDIA_ROOT = temp_dir
    
    yield
    
    # Очищаем после теста
    if temp_dir.exists():
        shutil.rmtree(temp_dir)