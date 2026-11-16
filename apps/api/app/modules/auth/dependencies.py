from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import PyJWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import has_permission, is_super_admin
from app.core.security import decode_access_token
from app.models.system import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录状态无效或已过期",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        subject = payload.get("sub")
        user_id = int(subject)
    except (PyJWTError, TypeError, ValueError):
        raise credentials_error from None

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or user.status != "ACTIVE":
        raise credentials_error

    return user


async def require_super_admin(user: User = Depends(get_current_user)) -> User:
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="仅超级管理员可访问")
    return user


def require_permission(permission_code: str) -> Callable:
    async def dependency(user: User = Depends(get_current_user)) -> User:
        if not has_permission(user, permission_code):
            raise HTTPException(status_code=403, detail="无权限执行此操作")
        return user

    return dependency

