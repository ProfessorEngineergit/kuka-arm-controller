import pytest

from app import config
from app.programs import run_program
from app.robot_state import robot
from app.servo_controller import UPDATE_HZ, servo
from tests.conftest import run


def test_move_clamps_to_joint_limits_and_state_matches():
    robot.enabled = True
    target = list(robot.joints)
    target[1] = 0          # J2 min is 30
    target[4] = 180        # gripper max is 90
    run(robot.move(target))
    assert robot.joints[1] == 30
    assert robot.joints[4] == 90


def test_per_joint_speed_cap():
    cfg = config.get()
    cfg["servos"]["default_speed"] = 1000   # try to exceed every servo limit
    servo.reload_config()
    # J2 is an MG996R with max_speed_dps 20 → 60° takes at least 3 s
    assert servo.motion_duration([90, 90, 90, 90, 0], [90, 150, 90, 90, 0], 100) == pytest.approx(3.0)


def test_home_is_interpolated_not_a_jump():
    robot.enabled = True
    robot.joints = [0.0, 90.0, 90.0, 90.0, 0.0]
    calls = []
    original = servo.set_all
    servo.set_all = lambda angles: calls.append(list(angles))
    try:
        run(robot.move_home())
    finally:
        servo.set_all = original
    assert robot.joints[0] == 90
    expected_steps = round(90 / servo.default_speed * UPDATE_HZ)
    assert len(calls) == expected_steps
    assert calls[0][0] < 1.0


def test_move_refused_when_disabled():
    robot.enabled = False
    before = list(robot.joints)
    assert run(robot.move([0, 30, 0, 0, 0])) is False
    assert robot.joints == before


def test_symbolic_program_targets_follow_calibration():
    robot.enabled = True
    cfg = config.get()
    cfg["joints"][1]["min_angle"] = 40
    servo.reload_config()
    run(run_program("rotate_all"))
    assert robot.joints == [float(j["home_angle"]) for j in cfg["joints"]]
    assert robot.running_program is None


def test_program_stop_holds_position_and_stays_enabled():
    robot.enabled = True

    async def scenario():
        import asyncio
        task = asyncio.create_task(run_program("rotate_all"))
        for _ in range(20):
            await asyncio.sleep(0)
        robot.program_abort = True
        await task

    run(scenario())
    assert robot.enabled is True
    assert robot.running_program is None
    assert robot.joints != [float(j["home_angle"]) for j in config.get()["joints"]]
