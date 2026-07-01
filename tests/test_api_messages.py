from fastapi.testclient import TestClient

from app.main import app


def test_post_message() -> None:
    with TestClient(app) as client:
        r = client.post(
            "/messages",
            json={"source": "ticket", "customer_id": "c1", "message": "Where is my order?"},
        )
        assert r.status_code == 200
    body = r.json()
    assert "trace_id" in body
    assert "response" in body
    assert "escalated" in body
