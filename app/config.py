"""Single loader for config/robot.yaml.

Every module reads the robot configuration through here, so a calibration or
backup restore (``reload()``) is seen by the servo controller, the kinematics
and the API at the same time.
"""
import os
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("KUKA_CONFIG", ROOT_DIR / "config" / "robot.yaml"))
PROGRAMS_DIR = Path(os.environ.get("KUKA_PROGRAMS_DIR", ROOT_DIR / "config" / "programs"))

JOINT_TYPES = ("revolute", "gripper")

_config = None


def get() -> dict:
    global _config
    if _config is None:
        _config = load_file(CONFIG_PATH)
    return _config


def reload() -> dict:
    """Re-read robot.yaml from disk (after calibration / backup restore)."""
    global _config
    _config = load_file(CONFIG_PATH)
    return _config


def load_file(path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def save(cfg: dict) -> None:
    """Write robot.yaml and make it the active configuration.

    Key order is preserved so the file stays readable after a calibration.
    """
    global _config
    tmp = CONFIG_PATH.with_suffix(".yaml.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    os.replace(tmp, CONFIG_PATH)
    _config = cfg


def joint_type(joint: dict) -> str:
    return joint.get("type", "revolute")


def arm_joint_ids(cfg: dict | None = None) -> list[int]:
    """Indices of the joints that are part of the kinematic chain."""
    cfg = cfg or get()
    return [i for i, j in enumerate(cfg["joints"]) if joint_type(j) == "revolute"]
