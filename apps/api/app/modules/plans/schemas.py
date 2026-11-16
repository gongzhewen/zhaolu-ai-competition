from pydantic import BaseModel, Field


class PlanUpsert(BaseModel):
    year_no: int = Field(ge=2000, le=2100)
    province_id: int
    batch_id: int
    subject_id: int
    major_id: int
    plan_type_id: int | None = None
    plan_count: int = Field(ge=0, le=100000)
    tuition: float | None = Field(default=None, ge=0, le=1000000)


class CopyPlanRequest(BaseModel):
    source_year: int = Field(ge=2000, le=2100)
    target_year: int = Field(ge=2000, le=2100)


class YearCreate(BaseModel):
    year_no: int = Field(ge=2000, le=2100)
