import asyncio
import yaml
from typing import List, Callable, Optional

_config = None

def _load_config():
    global _config
    if _config is None:
        with open("config/robot.yaml") as f:
            _config = yaml.safe_load(f)
    return _config


def _reload_config():
    """Force re-read of robot.yaml from disk (after calibration / backup restore)."""
    global _config
    with open("config/robot.yaml") as f:
        _config = yaml.safe_load(f)
    return _config


class ServoController:
    def __init__(self):
        cfg = _load_config()
        self.joints = cfg["joints"]
        self.freq = cfg["servos"]["frequency"]
        self.default_speed = cfg["servos"]["default_speed"]
        self._servo_types = cfg["servos"]["types"]
        self._pca = None
        self._mock = False
        self._init_hardware()

    def _init_hardware(self):
        try:
            import board
            from adafruit_pca9685 import PCA9685
            i2c = board.I2C()
            self._pca = PCA9685(i2c)
            self._pca.frequency = self.freq
            # Immediately hold home angles so servos don't twitch on reset
            for i, j in enumerate(self.joints):
                self.set_angle(i, j["home_angle"])
            print("[Servo] PCA9685 initialisiert")
        except Exception as e:
            print(f"[Servo] Hardware nicht verfügbar (Mock-Modus): {e}")
            self._mock = True

    def _pulse_range(self, joint_id: int) -> tuple[int, int]:
        """Returns (pulse_min_us, pulse_max_us) for the given joint's servo type."""
        j = self.joints[joint_id]
        stype = self._servo_types.get(j.get("servo_type", "mg996r"), {})
        return stype.get("pulse_min_us", 500), stype.get("pulse_max_us", 2500)

    def _angle_to_duty(self, joint_id: int, angle: float) -> int:
        """Converts angle to PCA9685 16-bit duty cycle using per-joint pulse range."""
        p_min, p_max = self._pulse_range(joint_id)
        pulse_us = p_min + (p_max - p_min) * (angle / 180.0)
        period_us = 1_000_000 / self.freq
        duty = int((pulse_us / period_us) * 0xFFFF)
        return max(0, min(0xFFFF, duty))

    def _clamp_angle(self, joint_id: int, angle: float) -> float:
        j = self.joints[joint_id]
        return max(j["min_angle"], min(j["max_angle"], angle))

    def set_angle(self, joint_id: int, angle: float):
        angle = self._clamp_angle(joint_id, angle)
        j = self.joints[joint_id]
        actual = (180.0 - angle) if j.get("invert") else angle
        if not self._mock and self._pca:
            self._pca.channels[j["channel"]].duty_cycle = self._angle_to_duty(joint_id, actual)

    def set_all(self, angles: List[float]):
        for i, angle in enumerate(angles):
            if i < len(self.joints):
                self.set_angle(i, angle)

    def stop_all(self):
        """Cuts PWM signal – servos hold last position (no torque loss on MG996R)."""
        if not self._mock and self._pca:
            for ch in self._pca.channels:
                ch.duty_cycle = 0

    def home(self):
        angles = [j["home_angle"] for j in self.joints]
        self.set_all(angles)
        return angles

    def reload_config(self):
        """Reload joint limits / servo types after calibration or backup restore."""
        cfg = _reload_config()
        self.joints = cfg["joints"]
        self.freq = cfg["servos"]["frequency"]
        self.default_speed = cfg["servos"]["default_speed"]
        self._servo_types = cfg["servos"]["types"]
        if not self._mock and self._pca:
            try:
                self._pca.frequency = self.freq
            except Exception:
                pass

    async def move_to(
        self,
        current: List[float],
        target: List[float],
        speed_pct: float = 100.0,
        should_abort: Optional[Callable[[], bool]] = None,
    ) -> List[float]:
        """Smoothly interpolate from current to target, respecting per-servo max speed.

        If ``should_abort()`` returns True at any point (E-Stop / disable), motion
        stops immediately, PWM is cut, and the last commanded position is returned
        so robot_state stays consistent with the physical arm.
        """
        speed = max(0.1, self.default_speed * (speed_pct / 100.0))
        max_delta = max((abs(t - c) for t, c in zip(target, current)), default=0) or 1
        steps = max(1, int(max_delta / speed * 20))  # 20 Hz update rate
        result = list(current)
        for i in range(1, steps + 1):
            if should_abort is not None and should_abort():
                self.stop_all()  # cut PWM – do NOT re-energize after E-Stop
                return result
            t = i / steps
            result = [c + (tgt - c) * t for c, tgt in zip(current, target)]
            self.set_all(result)
            await asyncio.sleep(1 / 20)
        return result


servo = ServoController()
