from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.ingestion import EtlJob, ImportRecord
from app.models.system import User
from app.modules.auth.dependencies import require_permission
from app.modules.ingestion.parser import SUPPORTED_SUFFIXES
from app.modules.ingestion.schemas import ImportJobResponse, ImportPreviewResponse, MappingRequest
from app.modules.ingestion.service import (
    commit_import_job,
    confirm_mapping_and_validate,
    create_import_job,
)

router = APIRouter()
MAX_FILE_SIZE = 50 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024


def _job_summary(job: EtlJob) -> ImportJobResponse:
    return ImportJobResponse(
        job_id=job.id,
        status=job.job_status,
        data_type=job.data_type,
        file_name=job.file_name,
        total_rows=job.total_rows,
        valid_rows=job.valid_rows,
        invalid_rows=job.invalid_rows,
        mapping_confirmed=job.mapping_confirmed,
        error_message=job.error_message,
    )


async def _get_job(db: AsyncSession, job_id: int) -> EtlJob:
    result = await db.execute(select(EtlJob).where(EtlJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="导入任务不存在")
    return job


_IMPORT_TEMPLATES = {
    "plan": {
        "filename": "plan_template.csv",
        "headers": "招生年度,省份,批次,科类,专业代码,专业名称,计划类型,计划数,学费,数据版本",
        "sample": "2026,湖南,本科批,物理类,080901,计算机科学与技术,普通类,120,6800,2026_v1",
    },
    "admission": {
        "filename": "admission_template.csv",
        "headers": "招生年度,省份,批次,科类,专业代码,专业名称,考生号,姓名,成绩/投档分,最低分,平均分,最高分,最低位次,是否报到,报到日期",
        "sample": "2026,湖南,本科批,物理类,080901,计算机科学与技术,24430101110001,示例考生,585,585,590,598,12000,是,2026-09-01",
    },
    "enrollment": {
        "filename": "enrollment_template.csv",
        "headers": "招生年度,考生号,姓名,是否报到,报到日期,备注",
        "sample": "2026,24430101110001,示例考生,是,2026-09-01,已按时报到",
    },
    "score_line": {
        "filename": "score_line_template.csv",
        "headers": "招生年度,省份,批次,科类,专业代码,专业名称,最低分,最低位次,计划数",
        "sample": "2026,湖南,本科批,物理类,080901,计算机科学与技术,585,12000,120",
    },
    "consultation": {
        "filename": "consultation_template.csv",
        "headers": "招生年度,省份,考生号,姓名,渠道,咨询类型,联系时间,是否转化,备注",
        "sample": "2026,湖南,24430101110001,示例考生,电话咨询,专业咨询,2026-06-18,是,已回访",
    },
}


@router.get("/template")
async def download_import_template(
    data_type: str = Query(default="plan", pattern="^(plan|admission|enrollment|score_line|consultation)$"),
    _user: User = Depends(require_permission("data:import")),
) -> Response:
    template = _IMPORT_TEMPLATES[data_type]
    content = f"\ufeff{template['headers']}\n{template['sample']}\n"
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={template['filename']}"},
    )


@router.get("/enrollment/template")
async def download_enrollment_template(
    _user: User = Depends(require_permission("data:import")),
) -> Response:
    content = "\ufeff招生年度,考生号,姓名,是否报到,报到日期,备注\n2026,24430101110001,示例考生,是,2026-09-01,已按时报到\n"
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=enrollment_template.csv"},
    )


@router.post("/imports", response_model=ImportJobResponse, status_code=202)
async def create_import(
    file: UploadFile = File(...),
    source_type: str = Form("file_upload"),
    data_type: str = Form("admission"),
    year: int | None = Form(default=None),
    data_version: str | None = Form(default=None),
    _user: User = Depends(require_permission("data:import")),
    db: AsyncSession = Depends(get_db),
) -> ImportJobResponse:
    original_name = Path(file.filename or "upload.bin").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=400, detail="仅支持 xlsx、xls、csv 文件")

    storage_dir = Path(settings.storage_root) / "imports"
    storage_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}{suffix}"
    stored_path = storage_dir / stored_name

    file_size = 0
    try:
        with stored_path.open("wb") as output:
            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                file_size += len(chunk)
                if file_size > MAX_FILE_SIZE:
                    raise HTTPException(status_code=413, detail="文件超过 50MB 限制")
                output.write(chunk)

        job = await create_import_job(
            db,
            file_path=stored_path,
            original_name=original_name,
            file_size=file_size,
            source_type=source_type,
            data_type=data_type,
            year=year,
            data_version=data_version,
        )
        return _job_summary(job)
    except HTTPException:
        stored_path.unlink(missing_ok=True)
        raise
    except ValueError as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise


@router.get("/imports/{job_id}", response_model=ImportJobResponse)
async def get_import(
    job_id: int,
    _user: User = Depends(require_permission("data:import")),
    db: AsyncSession = Depends(get_db),
) -> ImportJobResponse:
    return _job_summary(await _get_job(db, job_id))


@router.get("/imports/{job_id}/preview", response_model=ImportPreviewResponse)
async def get_import_preview(
    job_id: int,
    _user: User = Depends(require_permission("data:import")),
    db: AsyncSession = Depends(get_db),
) -> ImportPreviewResponse:
    job = await _get_job(db, job_id)
    return ImportPreviewResponse(
        job_id=job.id,
        headers=job.headers or [],
        mapping=job.mapping_data or {},
        preview=job.preview_data or [],
    )


@router.put("/imports/{job_id}/mapping", response_model=ImportJobResponse)
async def update_import_mapping(
    job_id: int,
    payload: MappingRequest,
    _user: User = Depends(require_permission("data:import")),
    db: AsyncSession = Depends(get_db),
) -> ImportJobResponse:
    job = await _get_job(db, job_id)
    if job.job_status in {"IMPORTING", "IMPORTED"}:
        raise HTTPException(status_code=409, detail="任务正在导入或已经完成，不能修改映射")

    try:
        job = await confirm_mapping_and_validate(db, job, payload.mapping)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _job_summary(job)


@router.post("/imports/{job_id}/commit", response_model=ImportJobResponse, status_code=202)
async def commit_import(
    job_id: int,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_permission("data:import")),
    db: AsyncSession = Depends(get_db),
) -> ImportJobResponse:
    job = await _get_job(db, job_id)
    if not job.mapping_confirmed:
        raise HTTPException(status_code=400, detail="请先确认字段映射并完成质量校验")
    if job.valid_rows <= 0:
        raise HTTPException(status_code=400, detail="没有可导入的有效数据")
    if job.job_status in {"IMPORTING", "IMPORTED"}:
        raise HTTPException(status_code=409, detail="任务正在导入或已经完成")

    job.job_status = "QUEUED_FOR_IMPORT"
    await db.commit()
    await db.refresh(job)
    background_tasks.add_task(commit_import_job, job.id)
    return _job_summary(job)


@router.get("/imports/{job_id}/issues")
async def list_import_issues(
    job_id: int,
    _user: User = Depends(require_permission("data:import")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get_job(db, job_id)
    result = await db.execute(
        select(ImportRecord)
        .where(ImportRecord.job_id == job_id, ImportRecord.status == "INVALID")
        .order_by(ImportRecord.row_no)
        .limit(500)
    )
    return {
        "items": [
            {
                "row_no": row.row_no,
                "raw_data": row.raw_data,
                "normalized_data": row.normalized_data,
                "error_message": row.error_message,
            }
            for row in result.scalars().all()
        ]
    }
