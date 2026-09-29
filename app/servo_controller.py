import asyncio
from typing import Callable, List, Optional

from app import config

UPDATE_HZ = 20


class ServoController:
    def __init__(self):
        self._apply_config(config.get())
        self._pca = None
        self._mock = False
        self._init_hardware()

    def _apply_config(self, cfg: dict):
        self.joints = cfg["joints"]
        self.freq = cfg["servos"]["frequency"]
        self.default_speed = float(cfg["servos"]["default_speed"])
        self._servo_types = cfg["servos"]["types"]

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

    @property
    def mock(self) -> bool:
        return self._mock

    def _servo_type(self, joint_id: int) -> dict:
        j = self.joints[joint_id]
        return self._servo_types.get(j.get("servo_type", "mg996r"), {})

    def _pulse_range(self, joint_id: int) -> tuple[int, int]:
        """Returns (pulse_min_us, pulse_max_us) for the given joint's servo type."""
        stype = self._servo_type(joint_id)
        return stype.get("pulse_min_us", 500), stype.get("pulse_max_us", 2500)

    def max_speed(self, joint_id: int) -> float:
        """Hard per-joint speed cap (°/s) from the servo type."""
        return float(self._servo_type(joint_id).get("max_speed_dps", self.default_speed))

    def _angle_to_duty(self, joint_id: int, angle: float) -> int:
        """Converts angle to PCA9685 16-bit duty cycle using per-joint pulse range."""
        p_min, p_max = self._pulse_range(joint_id)
        pulse_us = p_min + (p_max - p_min) * (angle / 180.0)
        period_us = 1_000_000 / self.freq
        duty = int((pulse_us / period_us) * 0xFFFF)
        return max(0, min(0xFFFF, duty))

    def clamp_angle(self, joint_id: int, angle: float) -> float:
        j = self.joints[joint_id]
        return max(j["min_angle"], min(j["max_angle"], angle))

    def clamp_all(self, angles: List[float]) -> List[float]:
        return [self.clamp_angle(i, a) if i < len(self.joints) else a
                for i, a in enumerate(angles)]

    def set_angle(self, joint_id: int, angle: float):
        angle = self.clamp_angle(joint_id, angle)
        j = self.joints[joint_id]
        actual = (180.0 - angle) if j.get("invert") else angle
        if not self._mock and self._pca:
            self._pca.channels[j["channel"]].duty_cycle = self._angle_to_duty(joint_id, actual)

    def set_all(self, angles: List[float]):
        for i, angle in enumerate(angles):
            if i < len(self.joints):
                self.set_angle(i, angle)

    def stop_all(self):
        """Cuts the PWM signal on every channel.

        Most analog hobby servos (MG996R, MG90S) go limp without a signal, so
        a loaded joint can sag after this. See README → Sicherheit.
        """
        if not self._mock and self._pca:
            for ch in self._pca.channels:
                ch.duty_cycle = 0

    def home_angles(self) -> List[float]:
        return [float(j["home_angle"]) for j in self.joints]

    def reload_config(self):
        """Reload joint limits / servo types after calibration or backup restore."""
        self._apply_config(config.get())
        if not self._mock and self._pca:
            try:
                self._pca.frequency = self.freq
            except Exception:
                pass

    def motion_duration(self, current: List[float], target: List[float], speed_pct: float) -> float:
        """Seconds a move takes: every joint stays at or below both the
        commanded speed (default_speed × speed_pct) and its servo's max_speed_dps."""
        speed = max(0.1, self.default_speed * (speed_pct / 100.0))
        duration = 0.0
        for i, (c, t) in enumerate(zip(current, target)):
            limit = min(speed, self.max_speed(i)) if i < len(self.joints) else speed
            duration = max(duration, abs(t - c) / max(0.1, limit))
        return duration

    async def move_to(
        self,
        current: List[float],
        target: List[float],
        speed_pct: float = 100.0,
        should_abort: Optional[Callable[[], bool]] = None,
    ) -> List[float]:
        """Smoothly interpolate from current to target.

        The target is clamped to the joint limits first, so the returned angles
        always match what the servos were actually commanded. If
        ``should_abort()`` returns True at any point (E-Stop / disable), motion
        stops immediately, PWM is cut, and the last commanded position is
        returned so robot_state stays consistent with the physical arm.
        """
        current = list(current)
        target = self.clamp_all(list(target))
        steps = max(1, round(self.motion_duration(current, target, speed_pct) * UPDATE_HZ))
        result = list(current)
        for i in range(1, steps + 1):
            if should_abort is not None and should_abort():
                self.stop_all()  # cut PWM – do NOT re-energize after E-Stop
                return result
            t = i / steps
            result = [c + (tgt - c) * t for c, tgt in zip(current, target)]
            self.set_all(result)
            await asyncio.sleep(1 / UPDATE_HZ)
        return result


servo = ServoController()
