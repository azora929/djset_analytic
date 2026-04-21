from fastapi import APIRouter, Depends, Request, Response

from app.core.config import AUTH_COOKIE_NAME, JWT_TTL_SEC
from app.models.schemas import AuthMeResponse, LoginRequest, LoginResponse
from app.services.auth import (
    authenticate_credentials,
    get_current_user,
    issue_access_token,
    revoke_access_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response) -> LoginResponse:
    if not authenticate_credentials(payload.username, payload.password):
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Неверный логин или пароль.")
    token = issue_access_token(payload.username)
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=JWT_TTL_SEC,
        httponly=True,
        samesite="lax",
        secure=False,
    )
    return LoginResponse(username=payload.username)


@router.get("/me", response_model=AuthMeResponse)
def me(username: str = Depends(get_current_user)) -> AuthMeResponse:
    return AuthMeResponse(username=username)


@router.post("/logout")
def logout(request: Request, response: Response, username: str = Depends(get_current_user)) -> dict:
    _ = username
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if token:
        try:
            revoke_access_token(token)
        except Exception:
            pass
    response.delete_cookie(AUTH_COOKIE_NAME)
    return {"ok": True}
