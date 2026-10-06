import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings  # noqa: E402
from app.store import Store  # noqa: E402


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, llm_provider="none", password="", ha_url="", ha_token="", ha_notify=[])


@pytest.fixture
def store(settings):
    s = Store(settings.db_path)
    yield s
    s.close()


@pytest.fixture(autouse=True)
def reset_language():
    from app import i18n
    i18n.set_default("de")
    i18n.set_lang(None)
    yield
    i18n.set_default("de")
    i18n.set_lang(None)
