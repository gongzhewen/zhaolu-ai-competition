from collections.abc import Iterable

from app.models.system import User

SUPER_ADMIN_ROLES = frozenset({"SUPER_ADMIN"})


def role_codes(user: User) -> set[str]:
    return {role.role_code for role in user.roles}


def has_role(user: User, required: str | Iterable[str]) -> bool:
    required_codes = {required} if isinstance(required, str) else set(required)
    return bool(role_codes(user) & required_codes)


def is_super_admin(user: User) -> bool:
    return has_role(user, SUPER_ADMIN_ROLES)




def permission_codes(user: User) -> set[str]:
    codes: set[str] = set()
    for role in user.roles:
        for permission in role.permissions:
            codes.add(permission.permission_code)
    return codes


def has_permission(user: User, permission_code: str) -> bool:
    return permission_code in permission_codes(user)


def has_any_permission(user: User, required: Iterable[str]) -> bool:
    available = permission_codes(user)
    return any(code in available for code in required)
