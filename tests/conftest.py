from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.config import Settings
from backend.api.main import create_app
from backend.store import LocalJsonStore


@pytest.fixture
def store(tmp_path: Path) -> LocalJsonStore:
    return LocalJsonStore(tmp_path / "data")


@pytest.fixture
def dist_dir(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('hi')", encoding="utf-8")
    return dist


@pytest.fixture
def client(tmp_path: Path, dist_dir: Path) -> TestClient:
    settings = Settings(_env_file=None, data_dir=tmp_path / "data", dashboard_dist=dist_dir)
    return TestClient(create_app(settings))
