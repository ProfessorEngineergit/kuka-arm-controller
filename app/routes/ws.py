import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth import require_auth_ws
from app.robot_state import robot
from app.servo_controller import servo
from app.coordinate_frames import compute_pose, jog_cartesian

router = APIRouter()

# Hard bounds: even a poisoned robot.yaml cannot drive a servo past the
# physical 0–180° hobby-servo range.
SERVO_MIN_ANGLE = 0.0
SERVO_MAX_ANGLE = 180.0
SPEED_MIN = 1.0
SPEED_MAX = 100.0
DELTA_MAX = 180.0          # one jog command may never request more than full sweep
CART_DELTA_MAX = 500.0     # mm / deg sanity cap for a single cartesian step


def _aborted() -> bool:
    return robot.estop or not robot.enabled


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


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    if not await require_auth_ws(websocket):
        await websocket.send_text(json.dumps({"type": "error", "msg": "Nicht angemeldet"}))
        await websocket.close(code=4401)
        return

    robot.register_ws(websocket)
    await robot.broadcast_state()

    try:
        async for raw in websocket.iter_text():
            try:
                msg = json.loads(raw)
                if not isinstance(msg, dict):
                    continue
            except Exception:
                continue

            try:
                await _handle_message(websocket, msg)
            except Exception as e:
                # One malformed/edge-case message must never kill the control
                # channel of a physical robot.
                try:
                    await websocket.send_text(json.dumps(
                        {"type": "error", "msg": f"Befehl ignoriert: {e}"}))
                except Exception:
                    pass

    except WebSocketDisconnect:
        pass
    finally:
        robot.unregister_ws(websocket)


async def _handle_message(websocket: WebSocket, msg: dict):
    mtype = msg.get("type")
    robot.touch()
    n = len(robot.joints)

    if mtype == "estop":
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
        robot.enabled = False
        servo.stop_all()
        await robot.broadcast_state()

    elif mtype == "jog":
        if robot.enabled and not robot.estop:
            joint = _joint_index(msg.get("joint", 0), n)
            if joint is None:
                return
            delta = _num(msg.get("delta", 0), 0.0, -DELTA_MAX, DELTA_MAX)
            speed = _num(msg.get("speed", 100), 100.0, SPEED_MIN, SPEED_MAX)
            async with robot.motion_lock:
                if _aborted():
                    return
                target = list(robot.joints)
                target[joint] = max(SERVO_MIN_ANGLE,
                                    min(SERVO_MAX_ANGLE, target[joint] + delta))
                new_joints = await servo.move_to(
                    robot.joints, target, speed, should_abort=_aborted)
                robot.joints = new_joints
                robot.pose = compute_pose(robot.joints)
            await robot.broadcast_state()

    elif mtype == "jog_abs":
        if robot.enabled and not robot.estop:
            joint = _joint_index(msg.get("joint", 0), n)
            if joint is None:
                return
            angle = _num(msg.get("angle", robot.joints[joint]),
                         robot.joints[joint], SERVO_MIN_ANGLE, SERVO_MAX_ANGLE)
            speed = _num(msg.get("speed", 100), 100.0, SPEED_MIN, SPEED_MAX)
            async with robot.motion_lock:
                if _aborted():
                    return
                target = list(robot.joints)
                target[joint] = angle
                new_joints = await servo.move_to(
                    robot.joints, target, speed, should_abort=_aborted)
                robot.joints = new_joints
                robot.pose = compute_pose(robot.joints)
            await robot.broadcast_state()

    elif mtype == "cartesian":
        if robot.enabled and not robot.estop:
            new_target = jog_cartesian(
                robot.joints,
                dx=_num(msg.get("dx", 0), 0.0, -CART_DELTA_MAX, CART_DELTA_MAX),
                dy=_num(msg.get("dy", 0), 0.0, -CART_DELTA_MAX, CART_DELTA_MAX),
                dz=_num(msg.get("dz", 0), 0.0, -CART_DELTA_MAX, CART_DELTA_MAX),
                da=_num(msg.get("da", 0), 0.0, -CART_DELTA_MAX, CART_DELTA_MAX),
                db=_num(msg.get("db", 0), 0.0, -CART_DELTA_MAX, CART_DELTA_MAX),
                dc=_num(msg.get("dc", 0), 0.0, -CART_DELTA_MAX, CART_DELTA_MAX),
                frame=msg.get("frame") if msg.get("frame") in ("WORLD", "TCP")
                else robot.active_frame,
            )
            speed = _num(msg.get("speed", 100), 100.0, SPEED_MIN, SPEED_MAX)
            async with robot.motion_lock:
                if _aborted():
                    return
                new_joints = await servo.move_to(
                    robot.joints, new_target, speed, should_abort=_aborted)
                robot.joints = new_joints
                robot.pose = compute_pose(robot.joints)
            await robot.broadcast_state()

    elif mtype == "frame":
        frame = msg.get("frame", "WORLD")
        if frame in ("WORLD", "TCP"):
            robot.active_frame = frame
            await robot.broadcast_state()

    elif mtype == "home":
        if robot.enabled and not robot.estop:
            async with robot.motion_lock:
                if _aborted():
                    return
                angles = servo.home()
                robot.joints = list(angles)
                robot.pose = compute_pose(robot.joints)
            await robot.broadcast_state()

    elif mtype == "ping":
        await websocket.send_text(json.dumps({"type": "pong"}))
