from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

ExportFormat = Literal["csv", "xlsx", "docx", "pdf", "md", "json"]
ExportKind = Literal[
    "query",
    "insights",
    "anomaly",
    "forecast",
    "simulation",
    "quality",
    "audit",
]


class ExportSection(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(default="", max_length=20000)


class ExportTable(BaseModel):
    columns: list[str] = Field(min_length=1, max_length=30)
    rows: list[list[Any]] = Field(default_factory=list, max_length=5000)

    @model_validator(mode="after")
    def validate_rows(self) -> ExportTable:
        for row in self.rows:
            if len(row) != len(self.columns):
                raise ValueError("每行单元格数量必须与列数一致")
        return self


class ResultExportRequest(BaseModel):
    kind: ExportKind = "query"
    format: ExportFormat
    title: str = Field(min_length=1, max_length=200)
    filename: str | None = Field(default=None, max_length=120)
    question: str | None = Field(default=None, max_length=4000)
    answer: str | None = Field(default=None, max_length=20000)
    sections: list[ExportSection] = Field(default_factory=list, max_length=50)
    metrics: dict[str, Any] = Field(default_factory=dict)
    table: ExportTable | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

