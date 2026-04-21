from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import redis
from fastapi import HTTPException, Request, WebSocket

from app.core.config import (
    AUTH_COOKIE_NAME,
    AUTH_LOGIN,
    AUTH_PASSWORD,
    AUTH_REDIS_URL,
    JWT_ALGORITHM,
    JWT_SECRET,
    JWT_TTL_SEC,
)

_redis = redis.Redis.from_url(AUTH_REDIS_URL, decode_responses=True)


def _session_key(jti: str) -> str:
    return f"auth:session:{jti}"


def authenticate_credentials(username: str, password: str) -> bool:
    return username == AUTH_LOGIN and password == AUTH_PASSWORD


def issue_access_token(username: str) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=JWT_TTL_SEC)
    jti = uuid4().hex
    payload = {
        "sub": username,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    _redis.set(_session_key(jti), username, ex=JWT_TTL_SEC)
    return token


def revoke_access_token(token: str) -> None:
    data = decode_access_token(token)
    jti = data.get("jti")
    if jti:
        _redis.delete(_session_key(jti))


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
    jti = data.get("jti")
    if not username or not jti:
        raise HTTPException(status_code=401, detail="Невалидный токен.")
    stored = _redis.get(_session_key(jti))
    if stored != username:
        raise HTTPException(status_code=401, detail="Сессия истекла.")
    return username


async def get_ws_current_user(websocket: WebSocket) -> str:
    token = websocket.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Требуется авторизация.")
    data = decode_access_token(token)
    username = data.get("sub")
    jti = data.get("jti")
    if not username or not jti:
        raise HTTPException(status_code=401, detail="Невалидный токен.")
    stored = _redis.get(_session_key(jti))
    if stored != username:
        raise HTTPException(status_code=401, detail="Сессия истекла.")
    return username
