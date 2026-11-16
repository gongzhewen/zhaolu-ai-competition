from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.system import User
from app.modules.auth.dependencies import require_permission
from app.modules.reports.schemas import ReportRequest
from app.modules.reports.service import build_report_context, generate_report_file

router = APIRouter()


def _remove_file(path: Path) -> None:
    path.unlink(missing_ok=True)


@router.get("")
async def list_reports() -> dict:
    return {"items": [], "message": "当前开发版采用即时生成模式，不保存历史报告"}


@router.post("/preview")
async def preview_report(
    payload: ReportRequest,
    _user: User = Depends(require_permission("report:export")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    context = await build_report_context(
        db,
        report_type=payload.report_type,
        year=payload.year,
        province=payload.province,
        major=payload.major,
    )
    return {
        "title": context["title"],
        "generated_at": context["generated_at"],
        "filters": context["filters"],
        "summary": context["summary"],
        "insights": context.get("insights", []),
        "ai_commentary": context.get("ai_commentary"),
        "admissions": context.get("admissions"),
        "source": context.get("source"),
        "trend": context.get("trend"),
        "candidate_profile": context.get("candidate_profile"),
        "subject_scores": context.get("subject_scores"),
        "major_choices": context.get("major_choices"),
        "medical": context.get("medical"),
        "anomalies": context.get("anomalies"),
    }


@router.post("/generate")
async def generate_report(
    payload: ReportRequest,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_permission("report:export")),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    context = await build_report_context(
        db,
        report_type=payload.report_type,
        year=payload.year,
        province=payload.province,
        major=payload.major,
    )
    path = generate_report_file(context, payload.file_format)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{context['title']}_{stamp}.{payload.file_format}"
    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if payload.file_format == "docx"
        else "application/pdf"
    )
    background_tasks.add_task(_remove_file, path)
    return FileResponse(path, media_type=media_type, filename=filename)
