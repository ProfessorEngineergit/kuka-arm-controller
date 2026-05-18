# Auth intentionally disabled – the controller runs on an isolated, single
# purpose Wi-Fi hotspot and the user explicitly does not want a login.
#
# These names exist only so the rest of the app (api.py imports them) keeps
# working without a login flow. They are deliberately inert.
from fastapi import Request, WebSocket

LOGIN_USER = "disabled"
LOGIN_PASSWORD = "disabled"
COOKIE_NAME = "kuka_session"


def require_auth(request: Request):
    pass  # open access


async def require_auth_ws(websocket: WebSocket) -> bool:
    return True


def create_session() -> str:
    return "open"


def invalidate_session() -> None:
    pass


def get_token_from_request(request: Request):
    return "open"


def validate_token(token) -> bool:
    return True
