import asyncio
import json
import time
from typing import List, Set

from app import config


def get_config():
    return config.get()


def reload_config():
    """Force re-read of robot.yaml after calibration / backup restore, and
    propagate the new limits to the live servo controller."""
    cfg = config.reload()
    from app.servo_controller import servo
    servo.reload_config()
    return cfg


class RobotState:
    def __init__(self):
        cfg = get_config()
        self.joints: List[float] = [float(j["home_angle"]) for j in cfg["joints"]]
        self.enabled: bool = False
        self.estop: bool = False
        self.estop_acknowledged: bool = True
        self.active_frame: str = "WORLD"  # "WORLD" or "TCP"
        self.pose: dict = {"x": 0.0, "y": 0.0, "z": 0.0, "a": 0.0, "b": 0.0, "c": 0.0}
        self.running_program: str | None = None
        self.program_abort: bool = False
        self.last_activity: float = time.time()
        self._websockets: Set = set()
        # Serializes physical motion so concurrent clients/tabs/programs cannot
        # issue conflicting servo commands at the same time.
        self.motion_lock = asyncio.Lock()

    def touch(self):
        self.last_activity = time.time()

    def aborted(self) -> bool:
        return self.estop or not self.enabled

    def register_ws(self, ws):
        self._websockets.add(ws)

    def unregister_ws(self, ws):
        self._websockets.discard(ws)

    async def broadcast(self, data: dict):
        msg = json.dumps(data)
        dead = set()
        for ws in list(self._websockets):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        self._websockets -= dead

    def state_dict(self) -> dict:
        return {
            "joints": self.joints,
            "pose": self.pose,
            "enabled": self.enabled,
            "estop": self.estop,
            "frame": self.active_frame,
            "program": self.running_program,
        }

    async def broadcast_state(self):
        await self.broadcast({"type": "state", **self.state_dict()})

    async def move(self, target: List[float], speed_pct: float = 100.0,
                   extra_abort=None) -> bool:
        """Move to ``target`` (clamped to the joint limits) under the motion
        lock. Returns False if the arm was not allowed to move."""
        from app.coordinate_frames import compute_pose
        from app.servo_controller import servo

        def should_abort() -> bool:
            return self.aborted() or bool(extra_abort and extra_abort())

        async with self.motion_lock:
            if should_abort():
                return False
            self.joints = await servo.move_to(
                self.joints, target, speed_pct, should_abort=should_abort)
            self.pose = compute_pose(self.joints)
        await self.broadcast_state()
        return True

    async def move_home(self, speed_pct: float = 100.0, extra_abort=None) -> bool:
        from app.servo_controller import servo
        return await self.move(servo.home_angles(), speed_pct, extra_abort)

    def trigger_estop(self):
        self.estop = True
        self.enabled = False
        self.estop_acknowledged = False
        self.program_abort = True

    def acknowledge_estop(self):
        if self.estop:
            self.estop = False
            self.estop_acknowledged = True

    def check_inactivity(self) -> bool:
        timeout = get_config()["security"]["inactivity_timeout_sec"]
        return (time.time() - self.last_activity) > timeout


robot = RobotState()
