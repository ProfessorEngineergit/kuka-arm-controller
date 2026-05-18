# Auth disabled – no login required
from fastapi import Request, WebSocket


def require_auth(request: Request):
    pass  # open access


async def require_auth_ws(websocket: WebSocket) -> bool:
    return True


def get_token_from_request(request: Request):
    return "open"


def validate_token(token) -> bool:
    return True
