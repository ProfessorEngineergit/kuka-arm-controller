import io
import zipfile

import pytest
import yaml
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.robot_state import robot


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_config_exposes_dh_table(client):
    body = client.get("/api/config").json()
    assert len(body["dh_parameters"]) == 5
    assert body["joints"][4]["type"] == "gripper"


def test_rest_jog_rejects_invalid_joint(client):
    robot.enabled = True
    assert client.post("/api/jog", json={"joint": 9, "angle": 10}).status_code == 400


@pytest.mark.parametrize("name", ["..", "a b", "x" * 65, "home"])
def test_program_save_rejects_bad_names(client, name):
    r = client.post(f"/api/programs/{name}/save",
                    json={"label": "x", "steps": [{"type": "home"}]})
    assert r.status_code in (400, 404, 405)


def test_program_save_validates_steps(client):
    r = client.post("/api/programs/test1/save",
                    json={"label": "x", "steps": [{"type": "jog", "joint": 7, "target": 1}]})
    assert r.status_code == 400
    r = client.post("/api/programs/test1/save",
                    json={"label": "x", "steps": [{"type": "jog", "joint": 1, "target": "max"}]})
    assert r.status_code == 200
    assert "test1" in client.get("/api/programs").json()


def test_run_unknown_program_is_404(client):
    robot.enabled = True
    assert client.post("/api/programs/nope/run").status_code == 404


def test_speed_is_validated(client):
    assert client.post("/api/config/speed", json={"speed": 0}).status_code == 400
    assert client.post("/api/config/speed", json={"speed": 500}).status_code == 400
    assert client.post("/api/config/speed", json={"speed": 12}).status_code == 200
    assert config.get()["servos"]["default_speed"] == 12


def test_calibration_keeps_file_structure(client):
    r = client.post("/api/calibrate", json={"joint": 1, "field": "min_angle", "value": 35})
    assert r.status_code == 200
    text = open(config.CONFIG_PATH, encoding="utf-8").read()
    assert text.index("servos:") < text.index("joints:") < text.index("dh_parameters:")
    assert config.get()["joints"][1]["min_angle"] == 35


def _backup(cfg):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("robot.yaml", yaml.safe_dump(cfg, sort_keys=False))
    return buf.getvalue()


def test_backup_rejects_duplicate_channels(client):
    cfg = config.load_file(config.CONFIG_PATH)
    cfg["joints"][0]["channel"] = cfg["joints"][1]["channel"]
    r = client.post("/api/backup/import", files={"file": ("b.zip", _backup(cfg), "application/zip")})
    assert r.status_code == 400
    assert "doppelt" in r.json()["detail"]


def test_backup_round_trip(client):
    data = client.get("/api/backup/export").content
    r = client.post("/api/backup/import", files={"file": ("b.zip", data, "application/zip")})
    assert r.status_code == 200
