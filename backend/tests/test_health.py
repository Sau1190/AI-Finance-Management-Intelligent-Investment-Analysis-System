from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_returns_service_info() -> None:
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["health"] == "/api/health"
    assert body["phase"] == 9


def test_health_endpoint_shape() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["phase"] == 9
    assert "does not promise" in body["disclaimer"].lower()
    assert "connected" in body["database"]
    # Database may be down during local setup; we never fake a connection.
    if not body["database"]["connected"]:
        assert body["status"] == "degraded"
        assert body["database"]["error"]
