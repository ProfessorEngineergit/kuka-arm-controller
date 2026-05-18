import asyncio
import time
from typing import List, Set
import yaml

_config = None

def get_config():
    global _config
    if _config is None:
        with open("config/robot.yaml") as f:
            _config = yaml.safe_load(f)
    return _config


def reload_config():
    """Force re-read of robot.yaml after calibration / backup restore, and
    propagate the new limits to the live servo controller."""
    global _config
    with open("config/robot.yaml") as f:
        _config = yaml.safe_load(f)
    from app.servo_controller import servo
    servo.reload_config()
    return _config


class RobotState:
    def __init__(self):
        cfg = get_config()
        self.joints: List[float] = [j["home_angle"] for j in cfg["joints"]]  # 5 joints
        self.enabled: bool = False
        self.estop: bool = False
        self.estop_acknowledged: bool = True
        self.active_frame: str = "WORLD"  # "WORLD" or "TCP"
        self.pose: dict = {"x": 0.0, "y": 0.0, "z": 0.0, "a": 0.0, "b": 0.0, "c": 0.0}
        self.running_program: str | None = None
        self.last_activity: float = time.time()
        self._websockets: Set = set()
        self._lock = asyncio.Lock()
        # Serializes physical motion so concurrent clients/tabs cannot issue
        # conflicting servo commands at the same time.
        self.motion_lock = asyncio.Lock()

    def touch(self):
        self.last_activity = time.time()

    def register_ws(self, ws):
        self._websockets.add(ws)

    def unregister_ws(self, ws):
        self._websockets.discard(ws)

    async def broadcast(self, data: dict):
        import json
        msg = json.dumps(data)
        dead = set()
        for ws in self._websockets:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        self._websockets -= dead

    async def broadcast_state(self):
        await self.broadcast({
            "type": "state",
            "joints": self.joints,
            "pose": self.pose,
            "enabled": self.enabled,
            "estop": self.estop,
            "frame": self.active_frame,
            "program": self.running_program,
        })

    def trigger_estop(self):
        self.estop = True
        self.enabled = False
        self.estop_acknowledged = False

    def acknowledge_estop(self):
        if self.estop:
            self.estop = False
            self.estop_acknowledged = True

    def check_inactivity(self) -> bool:
        cfg = get_config()
        timeout = cfg["security"]["inactivity_timeout_sec"]
        return (time.time() - self.last_activity) > timeout


robot = RobotState()
