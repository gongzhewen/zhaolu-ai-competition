from pydantic import BaseModel, Field


class StudentManagementUpdate(BaseModel):
    student_status: str | None = None
    follow_up_status: str | None = None
    owner_name: str | None = Field(default=None, max_length=128)
    tags: list[str] | None = None
    notes: str | None = None
