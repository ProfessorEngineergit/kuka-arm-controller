import asyncio
import os
import json
import zipfile
import io
from datetime import datetime
from fastapi import APIRouter, Request, Response, HTTPException, Depends, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List

from app.auth import (
    LOGIN_USER, LOGIN_PASSWORD, COOKIE_NAME,
    create_session, invalidate_session, require_auth, validate_token, get_token_from_request
)
from app import config
from app.robot_state import robot, get_config
from app.servo_controller import servo
from app.coordinate_frames import jog_cartesian
from app.programs import (list_programs, save_program, delete_program, run_program,
                          exists as program_exists, valid_name as valid_program_name)
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
    return {**robot.state_dict(), "mock": servo.mock}


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

def _require_motion_allowed():
    if not robot.enabled or robot.estop:
        raise HTTPException(status_code=400, detail="Arm nicht freigegeben")
    if robot.running_program:
        raise HTTPException(status_code=409, detail="Programm läuft – manuelles Verfahren gesperrt")
    robot.touch()


def _finite(value: float, lo: float, hi: float, what: str) -> float:
    if value != value or value in (float("inf"), float("-inf")):
        raise HTTPException(status_code=400, detail=f"Ungültiger Wert für {what}")
    return max(lo, min(hi, float(value)))


class JogRequest(BaseModel):
    joint: int
    angle: float
    speed: float = 100.0


@router.post("/api/jog")
async def jog(body: JogRequest, request: Request):
    require_auth(request)
    _require_motion_allowed()
    if not 0 <= body.joint < len(robot.joints):
        raise HTTPException(status_code=400, detail="Ungültiger Gelenk-Index")
    target = list(robot.joints)
    target[body.joint] = _finite(body.angle, 0.0, 180.0, "angle")
    await robot.move(target, _finite(body.speed, 1.0, 100.0, "speed"))
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
    _require_motion_allowed()
    deltas = {k: _finite(getattr(body, k), -500.0, 500.0, k)
              for k in ("dx", "dy", "dz", "da", "db", "dc")}
    target, reason = jog_cartesian(
        robot.joints, **deltas,
        frame=body.frame if body.frame in ("WORLD", "TCP") else "WORLD",
    )
    if reason:
        raise HTTPException(status_code=400, detail=reason)
    await robot.move(target, _finite(body.speed, 1.0, 100.0, "speed"))
    return {"joints": robot.joints, "pose": robot.pose}


# ─── Home ────────────────────────────────────────────────────────────────────

@router.post("/api/home")
async def go_home(request: Request):
    require_auth(request)
    _require_motion_allowed()
    await robot.move_home()
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


_program_tasks: set = set()


@router.post("/api/programs/{name}/run")
async def start_program(name: str, request: Request):
    require_auth(request)
    if not robot.enabled or robot.estop:
        raise HTTPException(status_code=400, detail="Arm nicht freigegeben")
    if robot.running_program:
        raise HTTPException(status_code=400, detail="Programm läuft bereits")
    if not program_exists(name):
        raise HTTPException(status_code=404, detail="Programm nicht gefunden")
    robot.touch()
    # Mark as running before the task starts so a second request can't race in.
    robot.running_program = name
    task = asyncio.create_task(run_program(name))
    _program_tasks.add(task)              # keep a reference until it finishes
    task.add_done_callback(_program_tasks.discard)
    return {"ok": True}


@router.post("/api/programs/stop")
async def stop_program(request: Request):
    """Stop the running program. The arm stays enabled and holds its current
    position (no PWM cut, so an unbalanced arm does not sag). E-Stop is the
    way to cut power."""
    require_auth(request)
    if robot.running_program:
        robot.program_abort = True
    await robot.broadcast_state()
    return {"ok": True}


class SaveProgramRequest(BaseModel):
    label: str
    description: str = ""
    steps: list


@router.post("/api/programs/{name}/save")
async def save_prog(name: str, body: SaveProgramRequest, request: Request):
    require_auth(request)
    try:
        save_program(name, body.label, body.description, body.steps)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.delete("/api/programs/{name}")
async def delete_prog(name: str, request: Request):
    require_auth(request)
    if not valid_program_name(name):
        raise HTTPException(status_code=400, detail="Ungültiger Programmname")
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
        "dh_parameters": cfg["dh_parameters"],
        "mock": servo.mock,
    }


class CalibrationRequest(BaseModel):
    joint: int
    field: str   # "home_angle" | "min_angle" | "max_angle"
    value: float


# Absolute mechanical limit of the hobby servos used on this arm. No
# calibration value may ever exceed this, regardless of what a client sends.
SERVO_ABS_MIN = 0.0
SERVO_ABS_MAX = 180.0


@router.post("/api/calibrate")
async def calibrate(body: CalibrationRequest, request: Request):
    require_auth(request)

    if body.field not in ("home_angle", "min_angle", "max_angle"):
        raise HTTPException(status_code=400, detail="Ungültiges Feld")

    cfg = config.load_file(config.CONFIG_PATH)

    joints = cfg.get("joints", [])
    if not isinstance(body.joint, int) or not (0 <= body.joint < len(joints)):
        raise HTTPException(status_code=400, detail="Ungültiger Gelenk-Index")

    # Reject NaN/Inf and clamp into the absolute mechanical servo range so a
    # calibration value can never command the servo past its physical stop.
    v = body.value
    if v != v or v in (float("inf"), float("-inf")):
        raise HTTPException(status_code=400, detail="Ungültiger Wert")
    v = max(SERVO_ABS_MIN, min(SERVO_ABS_MAX, float(v)))

    j = joints[body.joint]
    new_min = j.get("min_angle", 0)
    new_max = j.get("max_angle", 180)
    new_home = j.get("home_angle", 90)
    if body.field == "min_angle":
        new_min = v
    elif body.field == "max_angle":
        new_max = v
    else:
        new_home = v

    # Enforce a coherent, safe envelope: min < max, and home inside [min, max].
    if new_min >= new_max:
        raise HTTPException(
            status_code=400,
            detail=f"Min ({new_min}°) muss kleiner als Max ({new_max}°) sein",
        )
    if not (new_min <= new_home <= new_max):
        # Pull home back into the valid window instead of failing the whole save.
        new_home = max(new_min, min(new_max, new_home))

    j["min_angle"] = new_min
    j["max_angle"] = new_max
    j["home_angle"] = new_home

    config.save(cfg)

    # Apply immediately so the live servo controller respects the new limits
    # without requiring a restart.
    from app.robot_state import reload_config
    reload_config()

    return {"ok": True, "min_angle": new_min, "max_angle": new_max, "home_angle": new_home}


class SpeedRequest(BaseModel):
    speed: float  # degrees/sec


@router.post("/api/config/speed")
async def set_speed(body: SpeedRequest, request: Request):
    """Set default_speed (°/s). Capped at the fastest servo's max_speed_dps;
    each joint is additionally capped at its own servo's limit while moving."""
    require_auth(request)
    cfg = config.load_file(config.CONFIG_PATH)
    cap = max(float(t.get("max_speed_dps", 0)) for t in cfg["servos"]["types"].values())
    speed = body.speed
    if speed != speed or not 1.0 <= speed <= cap:
        raise HTTPException(status_code=400, detail=f"Geschwindigkeit muss zwischen 1 und {cap:g} °/s liegen")
    cfg["servos"]["default_speed"] = float(speed)
    config.save(cfg)
    from app.robot_state import reload_config
    reload_config()
    return {"ok": True, "speed": float(speed)}


# ─── Backup / Restore ─────────────────────────────────────────────────────────

@router.get("/api/backup/export")
async def export_backup(request: Request):
    """Export robot configuration and programs as ZIP file"""
    require_auth(request)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add robot.yaml
        if os.path.exists(config.CONFIG_PATH):
            with open(config.CONFIG_PATH, "r", encoding="utf-8") as f:
                zf.writestr("robot.yaml", f.read())

        # Add all program files
        programs_dir = str(config.PROGRAMS_DIR)
        if os.path.exists(programs_dir):
            for filename in os.listdir(programs_dir):
                if filename.endswith(".json"):
                    filepath = os.path.join(programs_dir, filename)
                    with open(filepath, "r") as f:
                        zf.writestr(f"programs/{filename}", f.read())

    zip_buffer.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"kuka-backup-{timestamp}.zip"

    return StreamingResponse(
        iter([zip_buffer.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# Backup hardening limits (defend against zip-bombs / memory exhaustion).
MAX_UPLOAD_BYTES = 2 * 1024 * 1024          # 2 MB compressed upload
MAX_TOTAL_UNCOMPRESSED = 10 * 1024 * 1024   # 10 MB total decompressed
MAX_ZIP_ENTRIES = 200
MAX_PROGRAM_BYTES = 256 * 1024              # 256 KB per program file


def _validate_robot_config(cfg: dict):
    """Reject a structurally-invalid or unsafe robot.yaml before it can reach
    the servo controller. A bad config here can physically damage hardware."""
    if not isinstance(cfg, dict):
        raise ValueError("robot.yaml: kein gültiges Objekt")

    joints = cfg.get("joints")
    if not isinstance(joints, list) or not joints:
        raise ValueError("robot.yaml: 'joints' fehlt oder leer")

    expected = len(robot.joints)
    if len(joints) != expected:
        raise ValueError(
            f"robot.yaml: {len(joints)} Gelenke, erwartet {expected}")

    channels = set()
    for idx, j in enumerate(joints):
        if not isinstance(j, dict):
            raise ValueError(f"Gelenk {idx}: ungültig")
        if j.get("type", "revolute") not in config.JOINT_TYPES:
            raise ValueError(f"Gelenk {idx}: unbekannter Typ '{j.get('type')}'")
        for key in ("channel", "min_angle", "max_angle", "home_angle"):
            if key not in j:
                raise ValueError(f"Gelenk {idx}: '{key}' fehlt")
        try:
            ch = int(j["channel"])
            mn = float(j["min_angle"])
            mx = float(j["max_angle"])
            hm = float(j["home_angle"])
        except (TypeError, ValueError):
            raise ValueError(f"Gelenk {idx}: nicht-numerische Werte")
        if not (0 <= ch <= 15):
            raise ValueError(f"Gelenk {idx}: Kanal {ch} außerhalb 0–15")
        if ch in channels:
            raise ValueError(f"Gelenk {idx}: Kanal {ch} ist doppelt belegt")
        channels.add(ch)
        if not (0.0 <= mn < mx <= 180.0):
            raise ValueError(
                f"Gelenk {idx}: ungültiger Bereich {mn}–{mx} (0 ≤ min < max ≤ 180)")
        if not (mn <= hm <= mx):
            raise ValueError(
                f"Gelenk {idx}: Home {hm}° außerhalb [{mn}, {mx}]")

    servos = cfg.get("servos")
    if not isinstance(servos, dict) or "frequency" not in servos:
        raise ValueError("robot.yaml: 'servos' Sektion fehlt/ungültig")

    dh = cfg.get("dh_parameters")
    if not isinstance(dh, list) or not dh:
        raise ValueError("robot.yaml: 'dh_parameters' fehlt oder leer")
    for idx, row in enumerate(dh):
        if not isinstance(row, list) or len(row) != 4:
            raise ValueError(f"DH-Zeile {idx + 1}: erwartet [a, alpha, d, theta_offset]")
        try:
            [float(v) for v in row]
        except (TypeError, ValueError):
            raise ValueError(f"DH-Zeile {idx + 1}: nicht-numerische Werte")


@router.post("/api/backup/import")
async def import_backup(request: Request, file: UploadFile = File(...)):
    """Restore robot configuration and programs from a ZIP file."""
    require_auth(request)

    # Bounded read: never load an unbounded upload into memory.
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Backup zu groß (max. 2 MB)")

    try:
        zip_buffer = io.BytesIO(content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            infos = zf.infolist()

            if len(infos) > MAX_ZIP_ENTRIES:
                raise HTTPException(status_code=400, detail="Zu viele Dateien im Backup")

            # Zip-bomb guard: reject before extracting anything.
            total = sum(i.file_size for i in infos)
            if total > MAX_TOTAL_UNCOMPRESSED:
                raise HTTPException(status_code=400, detail="Backup-Inhalt zu groß")

            names = zf.namelist()
            if "robot.yaml" not in names:
                raise HTTPException(
                    status_code=400, detail="robot.yaml nicht im Backup gefunden")

            # Validate robot.yaml fully BEFORE touching disk.
            robot_config_data = zf.read("robot.yaml").decode("utf-8")
            try:
                parsed = yaml.safe_load(robot_config_data)
            except yaml.YAMLError as e:
                raise HTTPException(
                    status_code=400, detail=f"Ungültiges YAML: {e}")
            _validate_robot_config(parsed)

            # Collect program files (zip-slip safe: basename only, size capped).
            programs_dir = str(config.PROGRAMS_DIR)
            restored_programs = []
            for info in infos:
                fn = info.filename
                if fn.startswith("programs/") and fn.endswith(".json"):
                    if info.file_size > MAX_PROGRAM_BYTES:
                        continue
                    safe_name = os.path.basename(fn)
                    if not valid_program_name(safe_name[:-5]):
                        continue
                    data = zf.read(fn)
                    try:
                        json.loads(data.decode("utf-8"))  # must be valid JSON
                    except Exception:
                        continue
                    restored_programs.append((safe_name, data))

            # All validation passed — commit changes.
            with open(config.CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write(robot_config_data)
            os.makedirs(programs_dir, exist_ok=True)
            for safe_name, data in restored_programs:
                with open(os.path.join(programs_dir, safe_name), "wb") as pf:
                    pf.write(data)

        # Apply restored limits to the live controller without a restart.
        from app.robot_state import reload_config
        reload_config()

        return {"ok": True, "message": "Backup erfolgreich wiederhergestellt"}

    except HTTPException:
        raise
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Ungültiges ZIP-Format")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Fehler beim Wiederherstellen: {e}")
