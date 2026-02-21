from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_request_id_added():
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.headers.get("X-Request-Id")


def test_request_id_propagation():
    request_id = "integration-test-request-id"

    response = client.get("/healthz", headers={"X-Request-Id": request_id})

    assert response.status_code == 200
    assert response.headers.get("X-Request-Id") == request_id


def test_healthz_ok():
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readyz_db_down(monkeypatch):
    async def _down():
        return False, "db_unavailable"

    monkeypatch.setattr("app.main.handle_readiness", _down)

    response = client.get("/readyz")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["reason"] == "db_unavailable"


def test_metrics_exposed():
    client.get("/healthz")
    response = client.get("/metrics/basic")

    assert response.status_code == 200
    payload = response.json()
    assert "request_latency_seconds" in payload
    assert "request_count_total" in payload
    assert "errors_total" in payload
