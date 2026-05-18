import asyncio
import json
import os
from typing import List, Optional
from app.robot_state import robot
from app.servo_controller import servo

PROGRAMS_DIR = "config/programs"


BUILTIN_PROGRAMS = {
    "home": {
        "label": "Home-Position",
        "description": "Alle Achsen auf Mittelposition",
        "steps": [{"type": "home"}],
    },
    "rotate_all": {
        "label": "Alle Achsen drehen",
        "description": "Dreht alle Gelenke sequenziell",
        # 5-DOF: J0 Metal-MG996R, J1 MG996R, J2-J4 MG90S
        "steps": [
            {"type": "jog", "joint": 0, "target": 0,   "speed": 25},
            {"type": "jog", "joint": 0, "target": 180, "speed": 25},
            {"type": "jog", "joint": 0, "target": 90,  "speed": 25},
            {"type": "jog", "joint": 1, "target": 30,  "speed": 20},
            {"type": "jog", "joint": 1, "target": 150, "speed": 20},
            {"type": "jog", "joint": 1, "target": 90,  "speed": 20},
            {"type": "jog", "joint": 2, "target": 0,   "speed": 30},
            {"type": "jog", "joint": 2, "target": 160, "speed": 30},
            {"type": "jog", "joint": 2, "target": 90,  "speed": 30},
            {"type": "jog", "joint": 3, "target": 0,   "speed": 40},
            {"type": "jog", "joint": 3, "target": 180, "speed": 40},
            {"type": "jog", "joint": 3, "target": 90,  "speed": 40},
            {"type": "home"},
        ],
    },
    "wave": {
        "label": "Winken",
        "description": "Schulter und Ellbogen winken",
        "steps": [
            {"type": "jog", "joint": 0, "target": 90,  "speed": 30},
            {"type": "jog", "joint": 1, "target": 60,  "speed": 20},
            {"type": "jog", "joint": 2, "target": 120, "speed": 50},
            {"type": "jog", "joint": 2, "target": 60,  "speed": 50},
            {"type": "jog", "joint": 2, "target": 120, "speed": 50},
            {"type": "jog", "joint": 2, "target": 60,  "speed": 50},
            {"type": "jog", "joint": 2, "target": 90,  "speed": 30},
            {"type": "home"},
        ],
    },
    "gripper_test": {
        "label": "Greifer Test",
        "description": "MG90S Greifer öffnen und schließen (J5)",
        "steps": [
            {"type": "jog", "joint": 4, "target": 0,  "speed": 40},
            {"type": "wait", "ms": 500},
            {"type": "jog", "joint": 4, "target": 90, "speed": 40},
            {"type": "wait", "ms": 500},
            {"type": "jog", "joint": 4, "target": 0,  "speed": 40},
        ],
    },
}


def list_programs() -> dict:
    programs = {k: {"label": v["label"], "description": v["description"], "builtin": True}
                for k, v in BUILTIN_PROGRAMS.items()}
    if os.path.isdir(PROGRAMS_DIR):
        for fname in os.listdir(PROGRAMS_DIR):
            if fname.endswith(".json"):
                key = fname[:-5]
                try:
                    with open(os.path.join(PROGRAMS_DIR, fname)) as f:
                        p = json.load(f)
                    programs[key] = {"label": p.get("label", key),
                                     "description": p.get("description", ""),
                                     "builtin": False}
                except Exception:
                    pass
    return programs


def save_program(name: str, label: str, description: str, steps: list):
    os.makedirs(PROGRAMS_DIR, exist_ok=True)
    with open(os.path.join(PROGRAMS_DIR, f"{name}.json"), "w") as f:
        json.dump({"label": label, "description": description, "steps": steps}, f, indent=2)


def delete_program(name: str) -> bool:
    path = os.path.join(PROGRAMS_DIR, f"{name}.json")
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


async def run_program(name: str):
    if name in BUILTIN_PROGRAMS:
        steps = BUILTIN_PROGRAMS[name]["steps"]
    else:
        path = os.path.join(PROGRAMS_DIR, f"{name}.json")
        if not os.path.exists(path):
            return
        with open(path) as f:
            data = json.load(f)
        steps = data["steps"]

    robot.running_program = name
    await robot.broadcast_state()

    try:
        for step in steps:
            if robot.estop or not robot.enabled:
                break
            await _execute_step(step)
    finally:
        robot.running_program = None
        await robot.broadcast_state()


async def _execute_step(step: dict):
    stype = step["type"]
    if stype == "home":
        target = servo.home()
        robot.joints = list(target)
        from app.coordinate_frames import compute_pose
        robot.pose = compute_pose(robot.joints)
        await robot.broadcast_state()

    elif stype == "jog":
        joint_id = step["joint"]
        target_angle = float(step["target"])
        speed = float(step.get("speed", 30))
        current = list(robot.joints)
        targets = list(current)
        targets[joint_id] = target_angle
        new_joints = await servo.move_to(current, targets, speed_pct=min(100, speed / servo.default_speed * 100))
        robot.joints = new_joints
        from app.coordinate_frames import compute_pose
        robot.pose = compute_pose(robot.joints)
        await robot.broadcast_state()

    elif stype == "wait":
        ms = int(step.get("ms", 100))
        await asyncio.sleep(ms / 1000)
