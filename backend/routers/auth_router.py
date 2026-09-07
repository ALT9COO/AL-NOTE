"""로그인 및 사용자/부서 조회 라우터."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from auth import (
    CurrentUser,
    DbSession,
    authenticate_user,
    create_access_token,
    hash_password,
    mark_password_state,
    verify_password,
    visible_departments,
    visible_users,
)
from rate_limit import reset, too_many
from schemas import DepartmentOut, LoginRequest, PasswordChangeRequest, TokenResponse, UserOut
from serializers import user_to_out

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: DbSession) -> TokenResponse:
    client = request.client.host if request.client else "unknown"
    bucket = f"login:{client}:{payload.user_id.strip().lower()}"
    if too_many(bucket, limit=8, window_sec=600):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="로그인 시도가 너무 많습니다. 10분 뒤 다시 시도하세요.",
        )
    user = authenticate_user(db, payload.user_id, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다.",
        )
    reset(bucket)
    token, expires_in = create_access_token(user, remember=payload.remember)
    return TokenResponse(access_token=token, expires_in=expires_in, user=user_to_out(user))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return user_to_out(user)


@router.post("/password")
def change_password(
    payload: PasswordChangeRequest, user: CurrentUser, db: DbSession
) -> dict[str, str]:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="현재 비밀번호가 올바르지 않습니다.",
        )
    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="새 비밀번호는 현재 비밀번호와 달라야 합니다.",
        )
    user.password_hash = hash_password(payload.new_password)
    mark_password_state(user, payload.new_password)
    db.commit()
    return {"message": "비밀번호를 변경했습니다."}


@router.get("/users", response_model=list[UserOut])
def list_users(user: CurrentUser, db: DbSession) -> list[UserOut]:
    """담당자 선택용 — 요청자의 RBAC 범위 내 사용자만 반환."""
    return [user_to_out(u) for u in visible_users(db, user)]


@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(user: CurrentUser, db: DbSession) -> list[DepartmentOut]:
    return [DepartmentOut.model_validate(d) for d in visible_departments(db, user)]
