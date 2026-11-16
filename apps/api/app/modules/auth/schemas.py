from pydantic import BaseModel, ConfigDict


class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str | None
    status: str
    roles: list[str]
    permissions: list[str]
    display_role: str = "系统用户"
