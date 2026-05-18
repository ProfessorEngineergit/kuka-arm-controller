import numpy as np
from typing import List
from app.kinematics import forward_kinematics, matrix_to_pose, inverse_kinematics


def compute_pose(joint_angles: List[float]) -> dict:
    T = forward_kinematics(joint_angles)
    return matrix_to_pose(T)


def jog_cartesian(
    joint_angles: List[float],
    dx: float = 0, dy: float = 0, dz: float = 0,
    da: float = 0, db: float = 0, dc: float = 0,
    frame: str = "WORLD",
) -> List[float]:
    """Move TCP by delta in World or TCP frame. Returns new joint angles or current if IK fails."""
    T_current = forward_kinematics(joint_angles)

    delta_pos = np.array([dx, dy, dz])
    if frame == "TCP":
        delta_pos = T_current[:3, :3] @ delta_pos

    T_target = T_current.copy()
    T_target[:3, 3] += delta_pos

    if any([da, db, dc]):
        import math
        Ra = _rot_z(math.radians(da))
        Rb = _rot_y(math.radians(db))
        Rc = _rot_x(math.radians(dc))
        if frame == "TCP":
            T_target[:3, :3] = T_target[:3, :3] @ Ra @ Rb @ Rc
        else:
            T_target[:3, :3] = Ra @ Rb @ Rc @ T_target[:3, :3]

    pose = matrix_to_pose(T_target)
    new_joints = inverse_kinematics(pose, initial_joints=joint_angles)
    return new_joints if new_joints else joint_angles


def _rot_z(a):
    return np.array([[np.cos(a), -np.sin(a), 0],
                     [np.sin(a),  np.cos(a), 0],
                     [0, 0, 1]])


def _rot_y(b):
    return np.array([[np.cos(b), 0, np.sin(b)],
                     [0, 1, 0],
                     [-np.sin(b), 0, np.cos(b)]])


def _rot_x(c):
    return np.array([[1, 0, 0],
                     [0, np.cos(c), -np.sin(c)],
                     [0, np.sin(c),  np.cos(c)]])
