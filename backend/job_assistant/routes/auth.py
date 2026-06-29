from __future__ import annotations

import logging

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from job_assistant.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    current_user,
    public_user,
    register_user,
    request_password_reset,
    reset_password,
    revoke_refresh_token,
    user_from_refresh_token,
)
from job_assistant.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class UserRegister(BaseModel):
    email: str
    password: str = Field(min_length=8)
    full_name: str = ""


class UserLogin(BaseModel):
    email: str
    password: str


class ForgotPasswordIn(BaseModel):
    email: str


class ResetPasswordIn(BaseModel):
    token: str
    password: str


def _auth_payload(user: dict, response: Response) -> dict:
    access_token = create_access_token(user)
    refresh_token = create_refresh_token(user, days=settings.refresh_token_expire_days)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=refresh_token,
        max_age=settings.session_cookie_max_age_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path=settings.session_cookie_path,
    )
    return {"access_token": access_token, "token_type": "bearer", "user": public_user(user)}


@router.post("/auth/register")
async def register(user_data: UserRegister, response: Response):
    try:
        user = register_user(user_data.email, user_data.password, user_data.full_name)
        return _auth_payload(user, response)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error registering user: {e}")
        raise HTTPException(status_code=500, detail="Failed to register user")


@router.post("/auth/login")
async def login(login_data: UserLogin, response: Response):
    user = authenticate_user(login_data.email, login_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _auth_payload(user, response)


@router.post("/auth/forgot-password")
async def forgot_password(payload: ForgotPasswordIn, request: Request):
    try:
        ip_address = ""
        user_agent = ""
        if request is not None:
            ip_address = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip() or (request.client.host if request.client else "")
            user_agent = request.headers.get("user-agent", "")
        request_password_reset(payload.email, settings.frontend_reset_password_url, ip_address=ip_address, user_agent=user_agent)
    except Exception as e:
        logger.error("Password reset request failed: %s", e)
        if settings.is_production:
            raise HTTPException(status_code=500, detail="Unable to process password reset request")
    return {"status": "success", "message": "If an account exists for that email, a password reset link has been sent."}


@router.post("/auth/reset-password")
async def reset_password_confirm(payload: ResetPasswordIn):
    try:
        if reset_password(payload.token, payload.password):
            return {"status": "success", "message": "Password has been reset."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    raise HTTPException(status_code=400, detail="Invalid or expired password reset token.")


@router.post("/auth/refresh")
async def refresh_auth(
    response: Response,
    refresh_token: str = Cookie(default="", alias=settings.session_cookie_name),
):
    user = user_from_refresh_token(refresh_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    revoke_refresh_token(refresh_token)
    return _auth_payload(user, response)


@router.post("/auth/logout")
async def logout(
    response: Response,
    refresh_token: str = Cookie(default="", alias=settings.session_cookie_name),
):
    if refresh_token:
        revoke_refresh_token(refresh_token)
    response.delete_cookie(
        key=settings.session_cookie_name,
        path=settings.session_cookie_path,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
    )
    return {"status": "success"}


@router.get("/auth/me")
async def me(user: dict = Depends(current_user)):
    return public_user(user)
