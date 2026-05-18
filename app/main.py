import asyncio
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routes.api import router as api_router
from app.routes.ws import router as ws_router
from app.robot_state import robot
from app.coordinate_frames import compute_pose


@asynccontextmanager
async def lifespan(app: FastAPI):
    robot.joints = [j["home_angle"] for j in __import__("app.robot_state", fromlist=["get_config"]).get_config()["joints"]]
    robot.pose = compute_pose(robot.joints)
    asyncio.create_task(_inactivity_watchdog())
    yield


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
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return FileResponse("static/app.html")
