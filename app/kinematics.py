import numpy as np
from typing import List, Optional
import yaml

_config = None
_dh_params = None


def _load_dh():
    global _config, _dh_params
    if _dh_params is None:
        with open("config/robot.yaml") as f:
            _config = yaml.safe_load(f)
        _dh_params = _config["dh_parameters"]
    return _dh_params


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


def forward_kinematics(joint_angles: List[float]) -> np.ndarray:
    """Returns 4x4 homogeneous transformation matrix (base → TCP)."""
    dh = _load_dh()
    T = np.eye(4)
    for i, (params, angle) in enumerate(zip(dh, joint_angles)):
        a, alpha, d, theta_offset = params
        theta = angle + theta_offset
        T = T @ _dh_matrix(a, alpha, d, theta)
    return T


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
    return {"x": round(x, 2), "y": round(y, 2), "z": round(z, 2),
            "a": round(rz, 2), "b": round(ry, 2), "c": round(rx, 2)}


def _pose_error(target_T: np.ndarray, current_T: np.ndarray) -> float:
    pos_err = np.linalg.norm(target_T[:3, 3] - current_T[:3, 3])
    rot_err = np.linalg.norm(target_T[:3, :3] - current_T[:3, :3], "fro")
    return pos_err + 10 * rot_err


def inverse_kinematics(target_pose: dict, initial_joints: Optional[List[float]] = None) -> Optional[List[float]]:
    """Numerical IK using scipy minimize. Returns joint angles in degrees or None."""
    try:
        from scipy.optimize import minimize
    except ImportError:
        return None

    with open("config/robot.yaml") as f:
        cfg = yaml.safe_load(f)
    joints_cfg = cfg["joints"]
    n = len(joints_cfg)

    target_T = _build_target_matrix(target_pose)
    x0 = initial_joints if initial_joints else [j["home_angle"] for j in joints_cfg]
    bounds = [(j["min_angle"], j["max_angle"]) for j in joints_cfg]

    def objective(angles):
        T = forward_kinematics(list(angles))
        return _pose_error(target_T, T)

    result = minimize(objective, x0, method="L-BFGS-B", bounds=bounds,
                      options={"maxiter": 500, "ftol": 1e-6})
    if result.fun < 5.0:
        return [round(float(a), 2) for a in result.x]
    return None


def _build_target_matrix(pose: dict) -> np.ndarray:
    x, y, z = pose.get("x", 0), pose.get("y", 0), pose.get("z", 0)
    a = np.radians(pose.get("a", 0))
    b = np.radians(pose.get("b", 0))
    c = np.radians(pose.get("c", 0))
    Rz = np.array([[np.cos(a), -np.sin(a), 0],
                   [np.sin(a),  np.cos(a), 0],
                   [0, 0, 1]])
    Ry = np.array([[np.cos(b), 0, np.sin(b)],
                   [0, 1, 0],
                   [-np.sin(b), 0, np.cos(b)]])
    Rx = np.array([[1, 0, 0],
                   [0, np.cos(c), -np.sin(c)],
                   [0, np.sin(c),  np.cos(c)]])
    R = Rz @ Ry @ Rx
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = [x, y, z]
    return T
