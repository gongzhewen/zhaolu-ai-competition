from pydantic import BaseModel, Field


class MajorAliasUpsert(BaseModel):
    source_name: str = Field(min_length=1, max_length=255)
    province_id: int | None = None
    canonical_major_id: int
    note: str | None = Field(default=None, max_length=1000)
    is_active: bool = True


class MajorRenameRequest(BaseModel):
    major_name: str = Field(min_length=1, max_length=255)
