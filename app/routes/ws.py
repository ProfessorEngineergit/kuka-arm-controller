import asyncio
import json
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth import require_auth_ws
from app.robot_state import robot
from app.servo_controller import servo
from app.coordinate_frames import jog_cartesian

router = APIRouter()

# Hard bounds: even a poisoned robot.yaml cannot drive a servo past the
# physical 0–180° hobby-servo range.
SERVO_MIN_ANGLE = 0.0
SERVO_MAX_ANGLE = 180.0
SPEED_MIN = 1.0
SPEED_MAX = 100.0
DELTA_MAX = 180.0          # one jog command may never request more than full sweep
CART_DELTA_MAX = 500.0     # mm / deg sanity cap for a single cartesian step

# Commands that move the arm. They are executed one at a time by a per-client
# worker; a newer command replaces one that is still waiting ("latest wins"),
# so a held jog key can never build up a backlog that keeps the arm moving
# after release. Everything else (E-Stop, disable, ...) is handled the moment
# it arrives, even while a motion is in progress.
MOTION_TYPES = ("jog", "jog_abs", "cartesian", "home")
# Messages that are not operator activity and must not reset the inactivity
# timeout (the browser pings every 25 s).
PASSIVE_TYPES = ("ping", "frame")
WARNING_INTERVAL_S = 1.0


def _num(value, default: float, lo: float, hi: float) -> float:
    """Parse a number from untrusted JSON, clamp to [lo, hi]. Never raises."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v != v or v in (float("inf"), float("-inf")):  # NaN / Inf guard
        return default
    return max(lo, min(hi, v))


def _joint_index(value, n: int):
    """Return a valid joint index in [0, n) or None if out of range / invalid."""
    try:
        j = int(value)
    except (TypeError, ValueError):
        return None
    if 0 <= j < n:
        return j
    return None


class _Client:
    def __init__(self, websocket: WebSocket):
        self.ws = websocket
        self.pending: dict | None = None
        self.wakeup = asyncio.Event()
        self._last_warning = ("", 0.0)

    async def send(self, data: dict):
        try:
            await self.ws.send_text(json.dumps(data))
        except Exception:
            pass

    async def warn(self, msg: str):
        """Send a warning, at most once per second for the same text."""
        text, ts = self._last_warning
        now = time.monotonic()
        if msg == text and now - ts < WARNING_INTERVAL_S:
            return
        self._last_warning = (msg, now)
        await self.send({"type": "warning", "msg": msg})

    def submit_motion(self, msg: dict):
        self.pending = msg
        self.wakeup.set()

    def drop_pending(self):
        self.pending = None

    async def motion_worker(self):
        while True:
            await self.wakeup.wait()
            self.wakeup.clear()
            msg, self.pending = self.pending, None
            if msg is None:
                continue
            try:
                await _execute_motion(self, msg)
            except Exception as e:
                await self.send({"type": "error", "msg": f"Befehl ignoriert: {e}"})


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    if not await require_auth_ws(websocket):
        await websocket.send_text(json.dumps({"type": "error", "msg": "Nicht angemeldet"}))
        await websocket.close(code=4401)
        return

    client = _Client(websocket)
    robot.register_ws(websocket)
    worker = asyncio.create_task(client.motion_worker())
    await client.send({"type": "state", **robot.state_dict()})

    try:
        async for raw in websocket.iter_text():
            try:
                msg = json.loads(raw)
                if not isinstance(msg, dict):
                    continue
            except Exception:
                continue

            try:
                await _handle_message(client, msg)
            except Exception as e:
                # One malformed/edge-case message must never kill the control
                # channel of a physical robot.
                await client.send({"type": "error", "msg": f"Befehl ignoriert: {e}"})

    except WebSocketDisconnect:
        pass
    finally:
        worker.cancel()
        robot.unregister_ws(websocket)


async def _handle_message(client: _Client, msg: dict):
    mtype = msg.get("type")
    if mtype not in PASSIVE_TYPES:
        robot.touch()

    if mtype == "estop":
        client.drop_pending()
        robot.trigger_estop()
        servo.stop_all()
        await robot.broadcast_state()

    elif mtype == "acknowledge":
        robot.acknowledge_estop()
        await robot.broadcast_state()

    elif mtype == "enable":
        if not robot.estop:
            robot.enabled = True
            await robot.broadcast_state()

    elif mtype == "disable":
        client.drop_pending()
        robot.enabled = False
        servo.stop_all()
        await robot.broadcast_state()

    elif mtype in MOTION_TYPES:
        if robot.aborted():
            return
        if robot.running_program:
            await client.warn("Programm läuft – manuelles Verfahren gesperrt")
            return
        client.submit_motion(msg)

    elif mtype == "frame":
        frame = msg.get("frame", "WORLD")
        if frame in ("WORLD", "TCP"):
            robot.active_frame = frame
            await robot.broadcast_state()

    elif mtype == "ping":
        await client.send({"type": "pong"})


async def _execute_motion(client: _Client, msg: dict):
    if robot.aborted() or robot.running_program:
        return
    mtype = msg.get("type")
    n = len(robot.joints)
    speed = _num(msg.get("speed", 100), 100.0, SPEED_MIN, SPEED_MAX)

    if mtype == "jog":
        joint = _joint_index(msg.get("joint", 0), n)
        if joint is None:
            return
        delta = _num(msg.get("delta", 0), 0.0, -DELTA_MAX, DELTA_MAX)
        target = list(robot.joints)
        target[joint] = max(SERVO_MIN_ANGLE, min(SERVO_MAX_ANGLE, target[joint] + delta))
        await robot.move(target, speed)

    elif mtype == "jog_abs":
        joint = _joint_index(msg.get("joint", 0), n)
        if joint is None:
            return
        angle = _num(msg.get("angle", robot.joints[joint]),
                     robot.joints[joint], SERVO_MIN_ANGLE, SERVO_MAX_ANGLE)
        target = list(robot.joints)
        target[joint] = angle
        await robot.move(target, speed)

    elif mtype == "cartesian":
        frame = msg.get("frame") if msg.get("frame") in ("WORLD", "TCP") else robot.active_frame
        target, reason = jog_cartesian(
            robot.joints,
            dx=_num(msg.get("dx", 0), 0.0, -CART_DELTA_MAX, CART_DELTA_MAX),
            dy=_num(msg.get("dy", 0), 0.0, -CART_DELTA_MAX, CART_DELTA_MAX),
            dz=_num(msg.get("dz", 0), 0.0, -CART_DELTA_MAX, CART_DELTA_MAX),
            da=_num(msg.get("da", 0), 0.0, -CART_DELTA_MAX, CART_DELTA_MAX),
            db=_num(msg.get("db", 0), 0.0, -CART_DELTA_MAX, CART_DELTA_MAX),
            dc=_num(msg.get("dc", 0), 0.0, -CART_DELTA_MAX, CART_DELTA_MAX),
            frame=frame,
        )
        if reason:
            await client.warn(reason)
            return
        await robot.move(target, speed)

    elif mtype == "home":
        await robot.move_home(speed)
