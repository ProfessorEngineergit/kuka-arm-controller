import os
import uuid
import time
from fastapi import Request, HTTPException, WebSocket
from fastapi.responses import JSONResponse

_active_token: str | None = None
_token_created: float = 0.0

LOGIN_USER = os.getenv("LOGIN_USER", "admin")
LOGIN_PASSWORD = os.getenv("LOGIN_PASSWORD", "kuka123")
COOKIE_NAME = "kuka_session"


def create_session() -> str:
    global _active_token, _token_created
    _active_token = str(uuid.uuid4())
    _token_created = time.time()
    return _active_token


def invalidate_session():
    global _active_token
    _active_token = None


def validate_token(token: str | None) -> bool:
    return token is not None and token == _active_token


def get_token_from_request(request: Request) -> str | None:
    return request.cookies.get(COOKIE_NAME)


def require_auth(request: Request):
    token = get_token_from_request(request)
    if not validate_token(token):
        raise HTTPException(status_code=401, detail="Nicht angemeldet")


async def require_auth_ws(websocket: WebSocket) -> bool:
    token = websocket.cookies.get(COOKIE_NAME)
    return validate_token(token)
