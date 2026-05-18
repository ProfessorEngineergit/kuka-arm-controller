import asyncio
import os
from fastapi import APIRouter, Request, Response, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List

from app.auth import (
    LOGIN_USER, LOGIN_PASSWORD, COOKIE_NAME,
    create_session, invalidate_session, require_auth, validate_token, get_token_from_request
)
from app.robot_state import robot, get_config
from app.servo_controller import servo
from app.coordinate_frames import compute_pose
from app.programs import list_programs, save_program, delete_program, run_program
import yaml

router = APIRouter()


# ─── Auth ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/api/login")
async def login(body: LoginRequest, response: Response):
    if body.username != LOGIN_USER or body.password != LOGIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Falsche Zugangsdaten")
    token = create_session()
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax")
    return {"ok": True}


@router.post("/api/logout")
async def logout(request: Request, response: Response):
    require_auth(request)
    invalidate_session()
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/api/auth-check")
async def auth_check(request: Request):
    token = get_token_from_request(request)
    return {"authenticated": validate_token(token)}


# ─── Status ─────────────────────────────────────────────────────────────────

@router.get("/api/status")
async def status(request: Request):
    require_auth(request)
    return {
        "joints": robot.joints,
        "pose": robot.pose,
        "enabled": robot.enabled,
        "estop": robot.estop,
        "frame": robot.active_frame,
        "program": robot.running_program,
    }


# ─── Enable / Disable / E-Stop ───────────────────────────────────────────────

@router.post("/api/enable")
async def enable(request: Request):
    require_auth(request)
    if robot.estop:
        raise HTTPException(status_code=400, detail="E-Stop aktiv – erst quittieren")
    robot.enabled = True
    robot.touch()
    await robot.broadcast_state()
    return {"ok": True}


@router.post("/api/disable")
async def disable(request: Request):
    require_auth(request)
    robot.enabled = False
    servo.stop_all()
    await robot.broadcast_state()
    return {"ok": True}


@router.post("/api/estop")
async def estop(request: Request):
    robot.trigger_estop()
    servo.stop_all()
    await robot.broadcast_state()
    return {"ok": True}


@router.post("/api/estop/acknowledge")
async def estop_acknowledge(request: Request):
    require_auth(request)
    robot.acknowledge_estop()
    await robot.broadcast_state()
    return {"ok": True}


# ─── Jog ────────────────────────────────────────────────────────────────────

class JogRequest(BaseModel):
    joint: int
    angle: float
    speed: float = 100.0


@router.post("/api/jog")
async def jog(body: JogRequest, request: Request):
    require_auth(request)
    if not robot.enabled or robot.estop:
        raise HTTPException(status_code=400, detail="Arm nicht freigegeben")
    robot.touch()
    target = list(robot.joints)
    target[body.joint] = body.angle
    new_joints = await servo.move_to(robot.joints, target, body.speed)
    robot.joints = new_joints
    robot.pose = compute_pose(robot.joints)
    await robot.broadcast_state()
    return {"joints": robot.joints, "pose": robot.pose}


# ─── Cartesian Jog ──────────────────────────────────────────────────────────

class CartesianJogRequest(BaseModel):
    dx: float = 0; dy: float = 0; dz: float = 0
    da: float = 0; db: float = 0; dc: float = 0
    frame: str = "WORLD"
    speed: float = 100.0


@router.post("/api/cartesian-jog")
async def cartesian_jog(body: CartesianJogRequest, request: Request):
    require_auth(request)
    if not robot.enabled or robot.estop:
        raise HTTPException(status_code=400, detail="Arm nicht freigegeben")
    robot.touch()
    from app.coordinate_frames import jog_cartesian
    new_joints = jog_cartesian(
        robot.joints,
        dx=body.dx, dy=body.dy, dz=body.dz,
        da=body.da, db=body.db, dc=body.dc,
        frame=body.frame,
    )
    new_joints = await servo.move_to(robot.joints, new_joints, body.speed)
    robot.joints = new_joints
    robot.pose = compute_pose(robot.joints)
    await robot.broadcast_state()
    return {"joints": robot.joints, "pose": robot.pose}


# ─── Home ────────────────────────────────────────────────────────────────────

@router.post("/api/home")
async def go_home(request: Request):
    require_auth(request)
    if not robot.enabled or robot.estop:
        raise HTTPException(status_code=400, detail="Arm nicht freigegeben")
    robot.touch()
    angles = servo.home()
    robot.joints = list(angles)
    robot.pose = compute_pose(robot.joints)
    await robot.broadcast_state()
    return {"ok": True}


# ─── Frame ───────────────────────────────────────────────────────────────────

@router.post("/api/frame/{frame}")
async def set_frame(frame: str, request: Request):
    require_auth(request)
    if frame not in ("WORLD", "TCP"):
        raise HTTPException(status_code=400, detail="Ungültiger Frame")
    robot.active_frame = frame
    await robot.broadcast_state()
    return {"frame": frame}


# ─── Programs ────────────────────────────────────────────────────────────────

@router.get("/api/programs")
async def get_programs(request: Request):
    require_auth(request)
    return list_programs()


@router.post("/api/programs/{name}/run")
async def start_program(name: str, request: Request):
    require_auth(request)
    if not robot.enabled or robot.estop:
        raise HTTPException(status_code=400, detail="Arm nicht freigegeben")
    if robot.running_program:
        raise HTTPException(status_code=400, detail="Programm läuft bereits")
    robot.touch()
    asyncio.create_task(run_program(name))
    return {"ok": True}


@router.post("/api/programs/stop")
async def stop_program(request: Request):
    require_auth(request)
    robot.running_program = None
    robot.enabled = False
    servo.stop_all()
    await robot.broadcast_state()
    return {"ok": True}


class SaveProgramRequest(BaseModel):
    label: str
    description: str = ""
    steps: list


@router.post("/api/programs/{name}/save")
async def save_prog(name: str, body: SaveProgramRequest, request: Request):
    require_auth(request)
    save_program(name, body.label, body.description, body.steps)
    return {"ok": True}


@router.delete("/api/programs/{name}")
async def delete_prog(name: str, request: Request):
    require_auth(request)
    if not delete_program(name):
        raise HTTPException(status_code=404, detail="Programm nicht gefunden")
    return {"ok": True}


# ─── Config ──────────────────────────────────────────────────────────────────

@router.get("/api/config")
async def get_robot_config(request: Request):
    require_auth(request)
    cfg = get_config()
    return {
        "joints": cfg["joints"],
        "servos": cfg["servos"],
    }


class CalibrationRequest(BaseModel):
    joint: int
    field: str   # "home_angle" | "min_angle" | "max_angle"
    value: float


@router.post("/api/calibrate")
async def calibrate(body: CalibrationRequest, request: Request):
    require_auth(request)
    cfg_path = "config/robot.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    if body.field not in ("home_angle", "min_angle", "max_angle"):
        raise HTTPException(status_code=400, detail="Ungültiges Feld")
    cfg["joints"][body.joint][body.field] = body.value
    with open(cfg_path, "w") as f:
        yaml.dump(cfg, f, allow_unicode=True)
    return {"ok": True}


class SpeedRequest(BaseModel):
    speed: float  # degrees/sec


@router.post("/api/config/speed")
async def set_speed(body: SpeedRequest, request: Request):
    require_auth(request)
    cfg_path = "config/robot.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    cfg["servos"]["default_speed"] = body.speed
    with open(cfg_path, "w") as f:
        yaml.dump(cfg, f, allow_unicode=True)
    servo.default_speed = body.speed
    return {"ok": True}
