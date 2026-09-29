import asyncio
import json

from app.robot_state import robot
from app.routes import ws
from tests.conftest import run


class FakeSocket:
    def __init__(self):
        self.sent = []

    async def send_text(self, text):
        self.sent.append(text)


def _client():
    return ws._Client(FakeSocket())


def test_held_jog_does_not_build_a_backlog():
    robot.enabled = True
    client = _client()

    async def scenario():
        for _ in range(40):
            await ws._handle_message(client, {"type": "jog", "joint": 0, "delta": 1})
        return client.pending

    pending = run(scenario())
    assert pending == {"type": "jog", "joint": 0, "delta": 1}, "only the latest jog may wait"


def test_estop_is_handled_immediately_and_drops_pending_motion():
    robot.enabled = True
    client = _client()

    async def scenario():
        await ws._handle_message(client, {"type": "jog", "joint": 0, "delta": 5})
        await ws._handle_message(client, {"type": "estop"})

    run(scenario())
    assert robot.estop is True and robot.enabled is False
    assert client.pending is None


def test_estop_interrupts_running_motion():
    robot.enabled = True
    client = _client()

    async def scenario():
        worker = asyncio.create_task(client.motion_worker())
        await ws._handle_message(client, {"type": "jog_abs", "joint": 0, "angle": 0, "speed": 100})
        for _ in range(5):
            await asyncio.sleep(0)
        await ws._handle_message(client, {"type": "estop"})
        for _ in range(5):
            await asyncio.sleep(0)
        worker.cancel()

    run(scenario())
    assert robot.estop
    assert 0 < robot.joints[0] < 90, "motion must stop part-way"


def test_ping_does_not_reset_inactivity_timer():
    client = _client()
    robot.last_activity = 0
    run(ws._handle_message(client, {"type": "ping"}))
    assert robot.last_activity == 0
    run(ws._handle_message(client, {"type": "enable"}))
    assert robot.last_activity > 0


def test_manual_motion_rejected_while_program_runs():
    robot.enabled = True
    robot.running_program = "wave"
    client = _client()
    run(ws._handle_message(client, {"type": "jog", "joint": 0, "delta": 5}))
    assert client.pending is None
    assert "Programm läuft" in json.loads(client.ws.sent[-1])["msg"]


def test_unreachable_cartesian_target_warns():
    robot.enabled = True
    client = _client()
    run(ws._execute_motion(client, {"type": "cartesian", "da": 5}))
    assert "A/C" in json.loads(client.ws.sent[-1])["msg"]
