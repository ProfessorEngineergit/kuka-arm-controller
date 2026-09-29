import numpy as np
import pytest

from app import config
from app.coordinate_frames import jog_cartesian
from app.kinematics import (IK_PITCH_TOL_DEG, IK_POS_TOL_MM, forward_kinematics,
                            inverse_kinematics, tool_pitch)


def test_gripper_does_not_move_tcp():
    """Audit finding 1: J5 has a=0, alpha=0 in the DH table, so it cannot move
    the TCP. It is a gripper, so it must not change the pose at all – neither
    position nor orientation."""
    for j5 in (0, 45, 90):
        assert np.allclose(forward_kinematics([90, 90, 90, 90, 0]),
                           forward_kinematics([90, 90, 90, 90, j5]))


def test_home_pose_matches_dh_table():
    T = forward_kinematics([90, 90, 90, 90, 0])
    # d1 = 60 up, a2 = 100 up, a3 = 90 and d5 = 55 back along -Y
    assert np.allclose(T[:3, 3], [0, -145, 160], atol=1e-9)


def test_only_arm_joints_are_kinematic():
    assert config.arm_joint_ids() == [0, 1, 2, 3]


def _random_arm(rng):
    joints = config.get()["joints"]
    q = [rng.uniform(j["min_angle"] + 10, j["max_angle"] - 10) for j in joints]
    return q


def test_ik_round_trip():
    rng = np.random.default_rng(42)
    for _ in range(100):
        q = _random_arm(rng)
        T = forward_kinematics(q)
        seed = [a + rng.uniform(-5, 5) for a in q]
        sol = inverse_kinematics(T[:3, 3], tool_pitch(q), seed)
        assert sol is not None
        assert np.linalg.norm(forward_kinematics(sol)[:3, 3] - T[:3, 3]) < IK_POS_TOL_MM
        assert abs(tool_pitch(sol) - tool_pitch(q)) < IK_PITCH_TOL_DEG
        assert sol[4] == seed[4], "IK must never move the gripper"


def test_ik_respects_joint_limits():
    joints = config.get()["joints"]
    rng = np.random.default_rng(7)
    for _ in range(50):
        q = _random_arm(rng)
        sol = inverse_kinematics(forward_kinematics(q)[:3, 3] + rng.uniform(-30, 30, 3),
                                 tool_pitch(q), q)
        if sol is None:
            continue
        for a, j in zip(sol, joints):
            assert j["min_angle"] - 1e-9 <= a <= j["max_angle"] + 1e-9


def test_ik_rejects_unreachable_target():
    assert inverse_kinematics([1000, 0, 0], 0, [90, 90, 90, 90, 0]) is None


@pytest.mark.parametrize("delta", [dict(dx=3), dict(dy=-3), dict(dz=3)])
def test_cartesian_jog_moves_exactly_by_delta(delta):
    q = [70, 100, 60, 100, 45]
    new, reason = jog_cartesian(q, **delta)
    assert reason is None
    moved = forward_kinematics(new)[:3, 3] - forward_kinematics(q)[:3, 3]
    expected = [delta.get("dx", 0), delta.get("dy", 0), delta.get("dz", 0)]
    assert np.allclose(moved, expected, atol=IK_POS_TOL_MM)
    assert abs(tool_pitch(new) - tool_pitch(q)) < IK_PITCH_TOL_DEG
    assert new[4] == 45


def test_cartesian_pitch_jog_keeps_tcp():
    q = [70, 100, 60, 100, 0]
    new, reason = jog_cartesian(q, db=5)
    assert reason is None
    assert np.allclose(forward_kinematics(new)[:3, 3], forward_kinematics(q)[:3, 3], atol=IK_POS_TOL_MM)
    assert abs(tool_pitch(new) - tool_pitch(q) - 5) < IK_PITCH_TOL_DEG


@pytest.mark.parametrize("delta", [dict(da=2), dict(dc=2)])
def test_uncontrollable_rotations_are_rejected(delta):
    q = [70, 100, 60, 100, 0]
    new, reason = jog_cartesian(q, **delta)
    assert new == q
    assert reason
