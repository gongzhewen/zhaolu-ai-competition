from pydantic import BaseModel, Field


class UserSummary(BaseModel):
    id: int
    username: str
    display_name: str | None
    status: str
    roles: list[str]


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=128)
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=128)
    role_codes: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    status: str | None = None
    role_codes: list[str] | None = None


class RoleSummary(BaseModel):
    id: int
    role_code: str
    role_name: str


class PermissionSummary(BaseModel):
    id: int
    permission_code: str
    permission_name: str
    permission_type: str


class RolePermissionUpdate(BaseModel):
    permission_codes: list[str] = Field(default_factory=list)
