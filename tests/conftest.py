"""Test setup: every test session works on a private copy of robot.yaml and an
empty programs directory, so tests never touch the real configuration, and
servo motion runs without real-time sleeps (no hardware → mock mode)."""
import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_tmp = Path(tempfile.mkdtemp(prefix="kuka-test-"))
shutil.copy(ROOT / "config" / "robot.yaml", _tmp / "robot.yaml")
os.environ["KUKA_CONFIG"] = str(_tmp / "robot.yaml")
os.environ["KUKA_PROGRAMS_DIR"] = str(_tmp / "programs")
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app import servo_controller  # noqa: E402
from app.robot_state import robot  # noqa: E402

_real_sleep = asyncio.sleep


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    """Restore the pristine config + robot state before each test."""
    shutil.copy(ROOT / "config" / "robot.yaml", _tmp / "robot.yaml")
    shutil.rmtree(_tmp / "programs", ignore_errors=True)
    config.reload()
    servo_controller.servo.reload_config()
    robot.joints = [float(j["home_angle"]) for j in config.get()["joints"]]
    robot.enabled = False
    robot.estop = False
    robot.running_program = None
    robot.program_abort = False
    robot._websockets.clear()

    async def fast_sleep(_delay=0, *args, **kwargs):
        await _real_sleep(0)

    monkeypatch.setattr(servo_controller.asyncio, "sleep", fast_sleep)
    yield


def run(coro):
    return asyncio.run(coro)
