"""Backend-ul servește interfața compilată pe Raspberry Pi, fără să afecteze API-ul."""

import pytest
from fastapi.testclient import TestClient

from src.backend.app import create_app


@pytest.fixture
def dist(tmp_path, monkeypatch):
    d = tmp_path / "dist"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text('<!doctype html><div id="root"></div>', encoding="utf-8")
    (d / "assets" / "app.js").write_text("console.log('ui')", encoding="utf-8")
    monkeypatch.setenv("FRONTEND_DIST", str(d))
    return d


def test_root_serves_index_html(dist):
    with TestClient(create_app()) as c:
        r = c.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert 'id="root"' in r.text


def test_assets_are_served(dist):
    with TestClient(create_app()) as c:
        r = c.get("/assets/app.js")
        assert r.status_code == 200
        assert "console.log" in r.text


def test_api_and_docs_still_have_priority(dist):
    with TestClient(create_app()) as c:
        assert c.get("/api/health").json()["status"] in {"ok", "degraded"}
        assert c.get("/api/weather").json()["meta"]["source"]
        assert c.get("/docs").status_code == 200


def test_websocket_still_works(dist):
    with TestClient(create_app()) as c:
        with c.websocket_connect("/ws") as ws:
            c.post("/api/refresh/weather")
            events = [ws.receive_json() for _ in range(2)]
            assert any(e["type"] == "data_updated" for e in events)


def test_files_outside_dist_are_not_served(dist):
    (dist.parent / "secret.env").write_text("DASHBOARD_PIN=1234", encoding="utf-8")
    with TestClient(create_app()) as c:
        for path in ["/../secret.env", "/%2e%2e/secret.env", "/assets/%2e%2e/%2e%2e/secret.env"]:
            r = c.get(path)
            assert "DASHBOARD_PIN" not in r.text, path


def test_without_build_only_api_is_served(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTEND_DIST", str(tmp_path / "nu-exista"))
    with TestClient(create_app()) as c:
        assert c.get("/").status_code == 404
        assert c.get("/api/health").status_code == 200
