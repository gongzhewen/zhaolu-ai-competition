from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import hash_password
from app.models.system import Permission, Role, User
from app.modules.auth.dependencies import require_permission
from app.modules.users.schemas import (
    PermissionSummary,
    RolePermissionUpdate,
    RoleSummary,
    UserCreate,
    UserSummary,
    UserUpdate,
)

router = APIRouter()


def _to_summary(user: User) -> UserSummary:
    return UserSummary(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        status=user.status,
        roles=[role.role_code for role in user.roles],
    )


async def _load_roles(db: AsyncSession, role_codes: list[str]) -> list[Role]:
    if not role_codes:
        return []
    result = await db.execute(select(Role).where(Role.role_code.in_(role_codes)))
    roles = list(result.scalars().all())
    if len(roles) != len(set(role_codes)):
        raise HTTPException(status_code=400, detail="存在无效角色编码")
    return roles


@router.get("", response_model=list[UserSummary])
async def list_users(
    _: User = Depends(require_permission("system:manage")),
    db: AsyncSession = Depends(get_db),
) -> list[UserSummary]:
    result = await db.execute(select(User).order_by(User.id))
    return [_to_summary(user) for user in result.scalars().all()]


@router.post("", response_model=UserSummary, status_code=201)
async def create_user(
    payload: UserCreate,
    _: User = Depends(require_permission("system:manage")),
    db: AsyncSession = Depends(get_db),
) -> UserSummary:
    exists = await db.execute(select(User).where(User.username == payload.username))
    if exists.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="用户名已存在")

    roles = await _load_roles(db, payload.role_codes)
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        status="ACTIVE",
        roles=roles,
    )
    db.add(user)
    await db.commit()

    created = await db.execute(select(User).where(User.id == user.id))
    return _to_summary(created.scalar_one())


@router.get("/roles", response_model=list[RoleSummary])
async def list_roles(
    _: User = Depends(require_permission("system:manage")),
    db: AsyncSession = Depends(get_db),
) -> list[RoleSummary]:
    result = await db.execute(select(Role).order_by(Role.id))
    return [
        RoleSummary(id=role.id, role_code=role.role_code, role_name=role.role_name)
        for role in result.scalars().all()
    ]


@router.get("/permissions", response_model=list[PermissionSummary])
async def list_permissions(
    _: User = Depends(require_permission("system:manage")),
    db: AsyncSession = Depends(get_db),
) -> list[PermissionSummary]:
    result = await db.execute(select(Permission).order_by(Permission.id))
    return [
        PermissionSummary(
            id=permission.id,
            permission_code=permission.permission_code,
            permission_name=permission.permission_name,
            permission_type=permission.permission_type,
        )
        for permission in result.scalars().all()
    ]


@router.get("/roles/{role_id}/permissions")
async def get_role_permissions(
    role_id: int,
    _: User = Depends(require_permission("system:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    return {
        "role_id": role.id,
        "role_code": role.role_code,
        "role_name": role.role_name,
        "permission_codes": [permission.permission_code for permission in role.permissions],
    }


@router.put("/roles/{role_id}/permissions")
async def update_role_permissions(
    role_id: int,
    payload: RolePermissionUpdate,
    _: User = Depends(require_permission("system:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail="角色不存在")

    permission_result = await db.execute(
        select(Permission).where(Permission.permission_code.in_(payload.permission_codes))
    )
    permissions = list(permission_result.scalars().all())
    if len(permissions) != len(set(payload.permission_codes)):
        raise HTTPException(status_code=400, detail="存在无效权限编码")

    role.permissions = permissions
    await db.commit()
    return {
        "role_id": role.id,
        "permission_codes": [permission.permission_code for permission in permissions],
    }


@router.patch("/{user_id}", response_model=UserSummary)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    _: User = Depends(require_permission("system:manage")),
    db: AsyncSession = Depends(get_db),
) -> UserSummary:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.status is not None:
        if payload.status not in {"ACTIVE", "DISABLED"}:
            raise HTTPException(status_code=400, detail="用户状态必须为 ACTIVE 或 DISABLED")
        user.status = payload.status
    if payload.role_codes is not None:
        user.roles = await _load_roles(db, payload.role_codes)

    await db.commit()
    updated = await db.execute(select(User).where(User.id == user.id))
    return _to_summary(updated.scalar_one())
