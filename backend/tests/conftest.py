from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import configure_database, init_db
from app.main import app


@pytest.fixture(autouse=True)
def test_env(tmp_path, monkeypatch) -> Generator[None, None, None]:
    db_file = tmp_path / "test.db"
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    exports = tmp_path / "exports"
    exports.mkdir()
    extracts = tmp_path / "extracts"
    extracts.mkdir()
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    market = tmp_path / "market"
    market.mkdir()
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///" + db_file.resolve().as_posix())
    monkeypatch.setenv("UPLOAD_DIR", str(uploads))
    monkeypatch.setenv("EXPORTS_DIR", str(exports))
    monkeypatch.setenv("EXTRACTS_DIR", str(extracts))
    monkeypatch.setenv("ANALYSIS_DIR", str(analysis))
    monkeypatch.setenv("MARKET_DIR", str(market))
    # Tests must never pick up a developer's real key from .env or the shell.
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "")
    monkeypatch.setenv("NEWS_API_KEY", "")
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "1024")
    get_settings.cache_clear()
    configure_database()
    init_db()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client
