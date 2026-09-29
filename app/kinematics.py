"""Forward / inverse kinematics from the DH table in config/robot.yaml.

Only joints with ``type: revolute`` are part of the kinematic chain. The
gripper (J5) opens and closes but does not move the TCP, so its DH row is
applied as a fixed transform (theta = theta_offset) and the IK never touches it.

The arm has four revolute axes (base yaw + three pitch axes in one plane), so a
TCP pose has four controllable coordinates: X, Y, Z and the tool pitch inside
the arm plane. The tool's yaw always follows the base rotation, and there is no
roll axis. The IK solves exactly those four coordinates.
"""
from typing import List, Optional, Sequence

import numpy as np

from app import config

# IK acceptance: a solution is only used if it really reaches the target.
IK_POS_TOL_MM = 0.5
IK_PITCH_TOL_DEG = 0.5
_IK_MAX_ITER = 100
_IK_PITCH_WEIGHT = 1.0   # mm of residual per degree of pitch error
_FD_STEP_DEG = 1e-4


def _dh_matrix(a: float, alpha_deg: float, d: float, theta_deg: float) -> np.ndarray:
    alpha = np.radians(alpha_deg)
    theta = np.radians(theta_deg)
    ca, sa = np.cos(alpha), np.sin(alpha)
    ct, st = np.cos(theta), np.sin(theta)
    return np.array([
        [ct,  -st*ca,  st*sa,  a*ct],
        [st,   ct*ca, -ct*sa,  a*st],
        [0,    sa,     ca,     d   ],
        [0,    0,      0,      1   ],
    ])


def _thetas(joint_angles: Sequence[float], cfg: dict) -> List[float]:
    """DH theta (deg) per row: servo angle + offset for arm joints, offset only
    for the gripper row and any row beyond the configured joints."""
    joints = cfg["joints"]
    out = []
    for i, (_a, _alpha, _d, offset) in enumerate(cfg["dh_parameters"]):
        moving = (i < len(joints) and i < len(joint_angles)
                  and config.joint_type(joints[i]) == "revolute")
        out.append((joint_angles[i] if moving else 0.0) + offset)
    return out


def frame_transforms(joint_angles: Sequence[float], cfg: Optional[dict] = None) -> List[np.ndarray]:
    """Cumulative base→frame_i transforms, one per DH row (the last is the TCP)."""
    cfg = cfg or config.get()
    T = np.eye(4)
    frames = []
    for (a, alpha, d, _offset), theta in zip(cfg["dh_parameters"], _thetas(joint_angles, cfg)):
        T = T @ _dh_matrix(a, alpha, d, theta)
        frames.append(T)
    return frames


def forward_kinematics(joint_angles: Sequence[float], cfg: Optional[dict] = None) -> np.ndarray:
    """Returns 4x4 homogeneous transformation matrix (base → TCP)."""
    frames = frame_transforms(joint_angles, cfg)
    return frames[-1] if frames else np.eye(4)


def matrix_to_pose(T: np.ndarray) -> dict:
    """Extracts X, Y, Z (mm) and Euler angles A, B, C (deg) from 4x4 matrix."""
    x, y, z = T[0, 3], T[1, 3], T[2, 3]
    sy = np.sqrt(T[0, 0]**2 + T[1, 0]**2)
    if sy > 1e-6:
        rx = np.degrees(np.arctan2(T[2, 1], T[2, 2]))
        ry = np.degrees(np.arctan2(-T[2, 0], sy))
        rz = np.degrees(np.arctan2(T[1, 0], T[0, 0]))
    else:
        rx = np.degrees(np.arctan2(-T[1, 2], T[1, 1]))
        ry = np.degrees(np.arctan2(-T[2, 0], sy))
        rz = 0.0
    return {"x": round(float(x), 2), "y": round(float(y), 2), "z": round(float(z), 2),
            "a": round(float(rz), 2), "b": round(float(ry), 2), "c": round(float(rx), 2)}


def tool_pitch(joint_angles: Sequence[float], cfg: Optional[dict] = None) -> float:
    """Signed angle (deg) of the tool approach axis inside the arm plane,
    measured from the horizontal. Independent of the base rotation."""
    frames = frame_transforms(joint_angles, cfg)
    return _pitch_from_frames(frames)


def _pitch_from_frames(frames: List[np.ndarray]) -> float:
    approach = frames[-1][:3, 2]
    up = np.array([0.0, 0.0, 1.0])
    normal = frames[0][:3, 2]            # J2 axis = normal of the arm plane
    radial = np.cross(up, normal)
    if np.linalg.norm(radial) < 1e-9:    # degenerate DH (vertical J2 axis)
        return float(np.degrees(np.arcsin(np.clip(approach[2], -1.0, 1.0))))
    radial /= np.linalg.norm(radial)
    return float(np.degrees(np.arctan2(approach @ up, approach @ radial)))


def _wrap_deg(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


def inverse_kinematics(
    target_xyz: Sequence[float],
    target_pitch: float,
    initial_joints: Sequence[float],
    cfg: Optional[dict] = None,
) -> Optional[List[float]]:
    """Solve the arm joints for a TCP position + in-plane tool pitch.

    Damped least squares seeded from ``initial_joints`` (so cartesian jogging
    stays on the current elbow branch), projected onto the joint limits.
    Non-arm joints (gripper) are returned unchanged. Returns None if the target
    is not reached within IK_POS_TOL_MM / IK_PITCH_TOL_DEG.
    """
    cfg = cfg or config.get()
    joints_cfg = cfg["joints"]
    arm = config.arm_joint_ids(cfg)
    lo = np.array([joints_cfg[i]["min_angle"] for i in arm], dtype=float)
    hi = np.array([joints_cfg[i]["max_angle"] for i in arm], dtype=float)
    target_xyz = np.asarray(target_xyz, dtype=float)

    full = [float(a) for a in initial_joints]

    def residual(q: np.ndarray) -> np.ndarray:
        angles = list(full)
        for k, i in enumerate(arm):
            angles[i] = q[k]
        frames = frame_transforms(angles, cfg)
        pos_err = frames[-1][:3, 3] - target_xyz
        pitch_err = _wrap_deg(_pitch_from_frames(frames) - target_pitch)
        return np.concatenate([pos_err, [_IK_PITCH_WEIGHT * pitch_err]])

    q = np.clip(np.array([full[i] for i in arm], dtype=float), lo, hi)
    lam = 1e-2
    r = residual(q)
    cost = r @ r
    for _ in range(_IK_MAX_ITER):
        if np.linalg.norm(r[:3]) < IK_POS_TOL_MM * 0.1 and abs(r[3]) < IK_PITCH_TOL_DEG * 0.1:
            break
        J = np.empty((len(r), len(q)))
        for k in range(len(q)):
            dq = np.zeros_like(q)
            dq[k] = _FD_STEP_DEG
            J[:, k] = (residual(q + dq) - r) / _FD_STEP_DEG
        JTJ = J.T @ J
        step = np.linalg.solve(JTJ + lam * np.diag(np.diag(JTJ) + 1e-9), -J.T @ r)
        q_new = np.clip(q + step, lo, hi)
        r_new = residual(q_new)
        cost_new = r_new @ r_new
        if cost_new < cost:
            q, r, cost = q_new, r_new, cost_new
            lam = max(lam / 3, 1e-7)
        else:
            lam *= 4
            if lam > 1e8:
                break

    if np.linalg.norm(r[:3]) > IK_POS_TOL_MM or abs(r[3]) / _IK_PITCH_WEIGHT > IK_PITCH_TOL_DEG:
        return None
    result = list(full)
    for k, i in enumerate(arm):
        result[i] = round(float(q[k]), 3)
    return result
