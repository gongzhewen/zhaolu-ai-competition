from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.models.system import User
from app.modules.audit.service import write_audit_log
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import AccessToken, UserProfile

router = APIRouter()


def _display_role(user: User) -> str:
    if "SUPER_ADMIN" in {role.role_code for role in user.roles}:
        return "超级管理员"
    return "、".join(role.role_name for role in user.roles) or "系统用户"


@router.post("/login", response_model=AccessToken)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> AccessToken:
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(form_data.password, user.password_hash):
        await write_audit_log(
            db,
            user_id=user.id if user else None,
            action_type="LOGIN",
            resource_type="USER",
            resource_id=form_data.username,
            request_data={"username": form_data.username},
            result_status="FAILED",
            ip_address=request.client.host if request.client else None,
        )
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if user.status != "ACTIVE":
        await write_audit_log(
            db,
            user_id=user.id,
            action_type="LOGIN",
            resource_type="USER",
            resource_id=str(user.id),
            request_data={"username": form_data.username},
            result_status="FAILED",
            ip_address=request.client.host if request.client else None,
        )
        raise HTTPException(status_code=403, detail="用户已被禁用")

    await write_audit_log(
        db,
        user_id=user.id,
        action_type="LOGIN",
        resource_type="USER",
        resource_id=str(user.id),
        request_data={"username": form_data.username},
        result_status="SUCCESS",
        ip_address=request.client.host if request.client else None,
    )
    token = create_access_token(
        str(user.id),
        {"username": user.username},
    )
    return AccessToken(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserProfile)
async def me(user: User = Depends(get_current_user)) -> UserProfile:
    role_codes = [role.role_code for role in user.roles]
    permission_codes = sorted(
        {permission.permission_code for role in user.roles for permission in role.permissions}
    )
    return UserProfile(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        status=user.status,
        roles=role_codes,
        permissions=permission_codes,
        display_role=_display_role(user),
    )


@router.post("/logout")
async def logout() -> dict[str, str]:
    return {"message": "前端清除令牌即可完成退出"}
