import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth import require_auth_ws
from app.robot_state import robot
from app.servo_controller import servo
from app.coordinate_frames import compute_pose, jog_cartesian

router = APIRouter()


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
            except Exception:
                continue

            mtype = msg.get("type")
            robot.touch()

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
                    joint = int(msg.get("joint", 0))
                    delta = float(msg.get("delta", 0))
                    speed = float(msg.get("speed", 100))
                    target = list(robot.joints)
                    target[joint] = target[joint] + delta
                    new_joints = await servo.move_to(robot.joints, target, speed)
                    robot.joints = new_joints
                    robot.pose = compute_pose(robot.joints)
                    await robot.broadcast_state()

            elif mtype == "jog_abs":
                if robot.enabled and not robot.estop:
                    joint = int(msg.get("joint", 0))
                    angle = float(msg.get("angle", robot.joints[joint]))
                    speed = float(msg.get("speed", 100))
                    target = list(robot.joints)
                    target[joint] = angle
                    new_joints = await servo.move_to(robot.joints, target, speed)
                    robot.joints = new_joints
                    robot.pose = compute_pose(robot.joints)
                    await robot.broadcast_state()

            elif mtype == "cartesian":
                if robot.enabled and not robot.estop:
                    new_joints = jog_cartesian(
                        robot.joints,
                        dx=float(msg.get("dx", 0)),
                        dy=float(msg.get("dy", 0)),
                        dz=float(msg.get("dz", 0)),
                        da=float(msg.get("da", 0)),
                        db=float(msg.get("db", 0)),
                        dc=float(msg.get("dc", 0)),
                        frame=msg.get("frame", robot.active_frame),
                    )
                    speed = float(msg.get("speed", 100))
                    new_joints = await servo.move_to(robot.joints, new_joints, speed)
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
                    angles = servo.home()
                    robot.joints = list(angles)
                    robot.pose = compute_pose(robot.joints)
                    await robot.broadcast_state()

            elif mtype == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        pass
    finally:
        robot.unregister_ws(websocket)
