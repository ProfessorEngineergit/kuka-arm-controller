import asyncio
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import config
from app.routes.api import router as api_router
from app.routes.ws import router as ws_router
from app.robot_state import robot
from app.coordinate_frames import compute_pose

STATIC_DIR = config.ROOT_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    robot.joints = [float(j["home_angle"]) for j in config.get()["joints"]]
    robot.pose = compute_pose(robot.joints)
    watchdog = asyncio.create_task(_inactivity_watchdog())
    yield
    watchdog.cancel()


async def _inactivity_watchdog():
    while True:
        await asyncio.sleep(30)
        if robot.enabled and robot.check_inactivity():
            robot.enabled = False
            from app.servo_controller import servo
            servo.stop_all()
            await robot.broadcast({"type": "warning", "msg": "Inaktivitäts-Timeout: Arm deaktiviert"})
            await robot.broadcast_state()


app = FastAPI(title="KUKA-ARM Controller", lifespan=lifespan)
app.include_router(api_router)
app.include_router(ws_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "app.html")
