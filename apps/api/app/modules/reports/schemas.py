from typing import Literal

from pydantic import BaseModel


class ReportRequest(BaseModel):
    report_type: Literal["admissions", "source", "comprehensive"] = "admissions"
    file_format: Literal["docx", "pdf"] = "docx"
    year: int | None = None
    province: str | None = None
    major: str | None = None
