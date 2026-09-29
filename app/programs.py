import asyncio
import json
import os
import re

from app import config
from app.robot_state import robot
from app.servo_controller import servo

PROGRAMS_DIR = str(config.PROGRAMS_DIR)


BUILTIN_PROGRAMS = {
    "home": {
        "label": "Home-Position",
        "description": "Alle Achsen auf Home-Position (robot.yaml)",
        "steps": [{"type": "home"}],
    },
    "rotate_all": {
        "label": "Alle Achsen drehen",
        "description": "Dreht alle Gelenke sequenziell",
        # Index 0–3 = J1–J4 (Arm-Achsen), der Greifer J5 hat ein eigenes
        # Programm. "min"/"max"/"home" werden zur Laufzeit aus robot.yaml
        # gelesen, das Programm folgt also jeder Kalibrierung.
        "steps": [
            step
            for joint, speed in ((0, 25), (1, 20), (2, 30), (3, 40))
            for step in (
                {"type": "jog", "joint": joint, "target": "min",  "speed": speed},
                {"type": "jog", "joint": joint, "target": "max",  "speed": speed},
                {"type": "jog", "joint": joint, "target": "home", "speed": speed},
            )
        ] + [{"type": "home"}],
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
        "description": "Greifer J5 öffnen und schließen",
        "steps": [
            {"type": "jog", "joint": 4, "target": "min",  "speed": 40},
            {"type": "wait", "ms": 500},
            {"type": "jog", "joint": 4, "target": "max",  "speed": 40},
            {"type": "wait", "ms": 500},
            {"type": "jog", "joint": 4, "target": "home", "speed": 40},
        ],
    },
}


NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
STEP_TYPES = ("home", "jog", "wait")
SYMBOLIC_TARGETS = {"min": "min_angle", "max": "max_angle", "home": "home_angle"}
MAX_STEPS = 1000


def valid_name(name: str) -> bool:
    return bool(NAME_RE.match(name or ""))


def validate_steps(steps) -> list:
    """Reject malformed programs at save time instead of at run time."""
    if not isinstance(steps, list) or not steps:
        raise ValueError("Programm enthält keine Schritte")
    if len(steps) > MAX_STEPS:
        raise ValueError(f"Zu viele Schritte (max. {MAX_STEPS})")
    n = len(robot.joints)
    for idx, step in enumerate(steps):
        if not isinstance(step, dict) or step.get("type") not in STEP_TYPES:
            raise ValueError(f"Schritt {idx + 1}: unbekannter Typ")
        if step["type"] == "jog":
            try:
                joint = int(step["joint"])
                if step["target"] not in SYMBOLIC_TARGETS:
                    float(step["target"])
                float(step.get("speed", 30))
            except (KeyError, TypeError, ValueError):
                raise ValueError(f"Schritt {idx + 1}: 'joint'/'target' fehlen oder ungültig")
            if not 0 <= joint < n:
                raise ValueError(f"Schritt {idx + 1}: Gelenk {joint} existiert nicht")
        if step["type"] == "wait":
            try:
                int(step.get("ms", 100))
            except (TypeError, ValueError):
                raise ValueError(f"Schritt {idx + 1}: 'ms' ungültig")
    return steps


def _program_path(name: str) -> str:
    return os.path.join(PROGRAMS_DIR, f"{name}.json")


def exists(name: str) -> bool:
    return name in BUILTIN_PROGRAMS or (valid_name(name) and os.path.exists(_program_path(name)))


def list_programs() -> dict:
    programs = {k: {"label": v["label"], "description": v["description"], "builtin": True}
                for k, v in BUILTIN_PROGRAMS.items()}
    if os.path.isdir(PROGRAMS_DIR):
        for fname in sorted(os.listdir(PROGRAMS_DIR)):
            if fname.endswith(".json"):
                key = fname[:-5]
                if key in BUILTIN_PROGRAMS or not valid_name(key):
                    continue
                try:
                    with open(os.path.join(PROGRAMS_DIR, fname)) as f:
                        p = json.load(f)
                    programs[key] = {"label": str(p.get("label", key)),
                                     "description": str(p.get("description", "")),
                                     "builtin": False}
                except Exception:
                    pass
    return programs


def save_program(name: str, label: str, description: str, steps: list):
    if not valid_name(name):
        raise ValueError("Ungültiger Programmname (erlaubt: A-Z a-z 0-9 _ -)")
    if name in BUILTIN_PROGRAMS:
        raise ValueError("Eingebaute Programme können nicht überschrieben werden")
    validate_steps(steps)
    os.makedirs(PROGRAMS_DIR, exist_ok=True)
    with open(_program_path(name), "w") as f:
        json.dump({"label": label, "description": description, "steps": steps}, f, indent=2)


def delete_program(name: str) -> bool:
    if not valid_name(name) or name in BUILTIN_PROGRAMS:
        return False
    path = _program_path(name)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def _load_steps(name: str) -> list | None:
    if name in BUILTIN_PROGRAMS:
        return BUILTIN_PROGRAMS[name]["steps"]
    if not valid_name(name):
        return None
    path = _program_path(name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f).get("steps", [])


def _stopped() -> bool:
    return robot.estop or not robot.enabled or robot.program_abort


async def run_program(name: str):
    try:
        steps = _load_steps(name)
    except (OSError, ValueError):
        steps = None
    if steps is None:
        robot.running_program = None
        await robot.broadcast_state()
        return

    robot.running_program = name
    robot.program_abort = False
    await robot.broadcast_state()

    try:
        for step in steps:
            if _stopped():
                break
            await _execute_step(step)
    finally:
        robot.running_program = None
        robot.program_abort = False
        await robot.broadcast_state()


async def _execute_step(step: dict):
    stype = step.get("type") if isinstance(step, dict) else None
    if stype == "home":
        await robot.move_home(extra_abort=lambda: robot.program_abort)

    elif stype == "jog":
        try:
            joint_id = int(step["joint"])
            speed = float(step.get("speed", 30))
            if not (0 <= joint_id < len(robot.joints)):
                return  # ignore poisoned / out-of-range step (e.g. from a restored backup)
            target = step["target"]
            if target in SYMBOLIC_TARGETS:
                target = config.get()["joints"][joint_id][SYMBOLIC_TARGETS[target]]
            target_angle = float(target)
        except (KeyError, TypeError, ValueError):
            return
        if target_angle != target_angle or speed != speed:  # NaN
            return
        # Program speeds are °/s; the servo controller additionally caps every
        # joint at default_speed and its servo's max_speed_dps.
        speed_pct = max(1.0, min(100.0, speed / max(0.1, servo.default_speed) * 100))
        targets = list(robot.joints)
        targets[joint_id] = target_angle  # clamped to the joint limits by move_to
        await robot.move(targets, speed_pct, extra_abort=lambda: robot.program_abort)

    elif stype == "wait":
        try:
            ms = int(step.get("ms", 100))
        except (TypeError, ValueError):
            ms = 100
        ms = max(0, min(60_000, ms))  # cap so a program can't sleep forever
        # Break the wait into slices so E-Stop interrupts promptly.
        deadline = asyncio.get_running_loop().time() + ms / 1000
        while True:
            if _stopped():
                return
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return
            await asyncio.sleep(min(0.1, remaining))
