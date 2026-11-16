from pydantic import BaseModel, Field


class MappingRequest(BaseModel):
    mapping: dict[str, str | None] = Field(default_factory=dict)


class ImportJobResponse(BaseModel):
    job_id: int
    status: str
    data_type: str | None
    file_name: str | None
    total_rows: int
    valid_rows: int
    invalid_rows: int
    mapping_confirmed: bool
    error_message: str | None = None


class ImportPreviewResponse(BaseModel):
    job_id: int
    headers: list[str]
    mapping: dict[str, str | None]
    preview: list[dict]
