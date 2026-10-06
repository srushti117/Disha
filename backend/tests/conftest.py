import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="disha_test_"))
os.environ["DATABASE_URL"] = os.environ.get("DISHA_TEST_DATABASE_URL") or f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["DATA_DIR"] = str(_tmp / "data")
os.environ["MODELS_DIR"] = str(_tmp / "models")
os.environ["DEMO_STEP_DELAY"] = "0"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def login(client, who="commander"):
    r = client.post("/api/auth/login", json={"email": f"{who}@disha.demo", "password": "Disha@2026"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def commander(client):
    return login(client, "commander")


@pytest.fixture(scope="session")
def analysed_event(client, commander):
    r = client.post("/api/events", json={"hazard": "flood", "aoi_method": "demo", "scenario_key": "kerala_flood_2018"}, headers=commander)
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    r = client.post(f"/api/events/{eid}/process", headers=commander)
    assert r.status_code == 202, r.text
    st = client.get(f"/api/events/{eid}/status", headers=commander).json()
    assert st["job"]["status"] == "succeeded", st
    return eid
