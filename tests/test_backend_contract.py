"""Teste de contract pentru API-ul backend (rulează pe serviciile mock)."""

import pytest
from fastapi.testclient import TestClient

from src.backend.app import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DASHBOARD_PIN", "4321")
    with TestClient(create_app()) as c:
        yield c


def _unlock(client) -> dict:
    r = client.post("/api/auth/unlock", json={"pin": "4321"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["schema_version"] == "1.0.0"


@pytest.mark.parametrize("path", ["/api/email", "/api/weather", "/api/news"])
def test_data_endpoints_use_envelope(client, path):
    body = client.get(path).json()
    assert set(body) == {"data", "meta"}
    assert {"source", "fetched_at", "age_seconds", "is_stale"} <= set(body["meta"])


def test_email_list_has_no_preview(client):
    items = client.get("/api/email").json()["data"]["items"]
    assert items and all("preview" not in e for e in items)


def test_email_filters(client):
    unread = client.get("/api/email?filter=unread").json()["data"]["items"]
    assert all(not e["is_read"] for e in unread)
    prio = client.get("/api/email?filter=priority").json()["data"]["items"]
    assert all(e["is_priority"] for e in prio)


def test_email_detail_requires_unlock(client):
    assert client.get("/api/email/mock-1").json()["code"] == "AUTH_REQUIRED"
    r = client.get("/api/email/mock-1", headers=_unlock(client))
    assert r.status_code == 200 and r.json()["data"]["preview"]


def test_wrong_pin_and_lockout(client):
    for _ in range(5):
        assert client.post("/api/auth/unlock", json={"pin": "0000"}).status_code == 401
    r = client.post("/api/auth/unlock", json={"pin": "4321"})
    assert r.status_code == 429 and r.json()["code"] == "LOCKED_OUT"


def test_lock_invalidates_session(client):
    h = _unlock(client)
    assert client.get("/api/auth/status", headers=h).json()["unlocked"] is True
    client.post("/api/auth/lock", headers=h)
    assert client.get("/api/auth/status", headers=h).json()["unlocked"] is False


def test_config_update_requires_unlock_and_rejects_duplicates(client):
    cfg = client.get("/api/config").json()
    assert client.put("/api/config", json=cfg).status_code == 401
    h = _unlock(client)
    cfg["widgets"][0]["enabled"] = False
    assert client.put("/api/config", json=cfg, headers=h).json()["widgets"][0]["enabled"] is False
    cfg["widgets"].append(cfg["widgets"][0])
    assert client.put("/api/config", json=cfg, headers=h).status_code == 422


def test_news_source_crud(client):
    h = _unlock(client)
    r = client.post("/api/news/sources", json={"name": "Test", "url": "https://example.com/rss"}, headers=h)
    assert r.status_code == 201
    sid = r.json()["id"]
    assert client.patch(f"/api/news/sources/{sid}", json={"enabled": False}, headers=h).json()["enabled"] is False
    assert client.delete(f"/api/news/sources/{sid}", headers=h).status_code == 204
    assert client.delete(f"/api/news/sources/{sid}", headers=h).status_code == 404


def test_telemetry(client):
    body = client.get("/api/system/telemetry").json()
    assert "cpu_load_pct" in body["system"] and len(body["sources"]) == 3


def test_websocket_receives_events(client):
    with client.websocket_connect("/ws") as ws:
        client.post("/api/refresh/weather")
        events = [ws.receive_json() for _ in range(2)]
        assert any(e["type"] == "data_updated" and e["payload"]["widget"] == "weather" for e in events)
