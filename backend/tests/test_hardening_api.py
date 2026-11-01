"""Phase 14 API-level regression tests (need the real FastAPI stack and the
suite's conftest fixtures). The framework-free logic behind each behaviour is
covered by test_hardening_units.py; these confirm the wiring in app.main.
"""

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app


def test_unknown_url_uses_the_error_envelope_and_is_not_an_empty_state(client):
    response = client.get("/api/definitely-not-a-route")
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert set(detail) == {"code", "message"}
    assert "NOT_FOUND" not in detail["code"]  # the dashboard treats *_NOT_FOUND as "nothing yet"


def test_responses_carry_hardening_headers(client):
    response = client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"


def test_cors_is_not_credentialed_and_only_allows_the_dashboard_origin(client):
    allowed = client.options(
        "/api/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-credentials" not in allowed.headers
    other = client.options(
        "/api/health",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in other.headers


def test_a_huge_upload_is_refused_with_413_before_it_is_parsed(client):
    # MAX_UPLOAD_BYTES is 1024 in the test environment; the cap is that plus 64 KB framing.
    response = client.post("/api/files", files={"file": ("big.csv", b"a,b\n" + b"1,2\n" * 40_000, "text/csv")})
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "FILE_TOO_LARGE"


def test_a_slightly_oversized_upload_keeps_the_existing_400_answer(client):
    response = client.post("/api/files", files={"file": ("big.csv", b"a,b\n" + b"1,2\n" * 400, "text/csv")})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "FILE_TOO_LARGE"


def test_an_oversized_json_body_is_refused(client):
    response = client.post("/api/sentiment/AAA/text", content=b"x" * (2 * 1024 * 1024 + 10), headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "REQUEST_TOO_LARGE"


def test_database_and_unexpected_errors_get_the_envelope_without_internal_text():
    def database_down():
        raise OperationalError("SELECT secret FROM t WHERE password='SECRET123'", {}, Exception("boom SECRET123"))

    def unexpected():
        raise RuntimeError("path C:\\secret\\file.csv SECRET123")

    app.add_api_route("/api/__test_db_down", database_down)
    app.add_api_route("/api/__test_unexpected", unexpected)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        down = test_client.get("/api/__test_db_down")
        assert down.status_code == 503 and down.json()["detail"]["code"] == "DATABASE_FAILURE"
        broken = test_client.get("/api/__test_unexpected")
        assert broken.status_code == 500 and broken.json()["detail"]["code"] == "INTERNAL_ERROR"
        for response in (down, broken):
            assert "SECRET123" not in response.text
