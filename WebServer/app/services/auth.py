from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Request, WebSocket

from app.core.config import (
    AUTH_COOKIE_NAME,
    AUTH_LOGIN,
    AUTH_PASSWORD,
    JWT_ALGORITHM,
    JWT_SECRET,
    JWT_TTL_SEC,
)


def authenticate_credentials(username: str, password: str) -> bool:
    return username == AUTH_LOGIN and password == AUTH_PASSWORD


def issue_access_token(username: str) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=JWT_TTL_SEC)
    payload = {
        "sub": username,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def revoke_access_token(token: str) -> None:
    _ = token
    return None


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Невалидный токен.") from exc


def get_current_user(request: Request) -> str:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Требуется авторизация.")
    data = decode_access_token(token)
    username = data.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Невалидный токен.")
    return username


async def get_ws_current_user(websocket: WebSocket) -> str:
    token = websocket.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Требуется авторизация.")
    data = decode_access_token(token)
    username = data.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Невалидный токен.")
    return username
