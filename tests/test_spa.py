import pytest
from fastapi.testclient import TestClient

from backend.api.config import Settings
from backend.api.main import create_app


@pytest.mark.parametrize("path", ["/", "/styleguide", "/orders/abc123"])
def test_spa_routes_return_index(client, path):
    res = client.get(path)
    assert res.status_code == 200
    assert "<div id=root>" in res.text


def test_real_asset_is_served(client):
    res = client.get("/assets/app.js")
    assert res.status_code == 200
    assert "console.log" in res.text


def test_missing_asset_is_404(client):
    assert client.get("/assets/missing.js").status_code == 404


@pytest.mark.parametrize("path", ["/api/nope", "/mcp", "/mcp/x", "/.well-known/ucp"])
def test_reserved_prefixes_never_fall_back(client, path):
    res = client.get(path)
    assert res.status_code == 404
    assert res.headers["content-type"].startswith("application/json")


def test_path_traversal_is_blocked(client, tmp_path):
    (tmp_path / "secret.txt").write_text("top secret", encoding="utf-8")
    res = client.get("/%2e%2e/secret.txt")
    assert "top secret" not in res.text


def test_unbuilt_dashboard_gives_hint(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path / "d", dashboard_dist=tmp_path / "nope")
    res = TestClient(create_app(settings)).get("/")
    assert res.status_code == 503
    assert "scripts/build.ps1" in res.text
