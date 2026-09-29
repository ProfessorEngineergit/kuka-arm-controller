from typing import List, Optional, Tuple

import numpy as np

from app.kinematics import forward_kinematics, inverse_kinematics, matrix_to_pose, tool_pitch


def compute_pose(joint_angles: List[float]) -> dict:
    T = forward_kinematics(joint_angles)
    return matrix_to_pose(T)


def jog_cartesian(
    joint_angles: List[float],
    dx: float = 0, dy: float = 0, dz: float = 0,
    da: float = 0, db: float = 0, dc: float = 0,
    frame: str = "WORLD",
) -> Tuple[List[float], Optional[str]]:
    """Move the TCP by a delta in the World or TCP frame.

    Returns ``(new_joints, None)`` on success, or ``(joint_angles, reason)`` if
    the target cannot be reached. The arm has four axes, so only X/Y/Z and the
    tool pitch (B) are controllable; A (yaw) follows the base and there is no
    roll axis (C).
    """
    if da or dc:
        return joint_angles, "A/C nicht verfahrbar: 4-Achs-Arm (Gier folgt J1, J5 ist Greifer)"

    T_current = forward_kinematics(joint_angles)
    delta_pos = np.array([dx, dy, dz], dtype=float)
    if frame == "TCP":
        delta_pos = T_current[:3, :3] @ delta_pos

    target_xyz = T_current[:3, 3] + delta_pos
    target_pitch = tool_pitch(joint_angles) + db

    new_joints = inverse_kinematics(target_xyz, target_pitch, joint_angles)
    if new_joints is None:
        return joint_angles, "Ziel außerhalb des Arbeitsraums oder der Achsgrenzen"
    return new_joints, None
