from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.dbf_import import DbfImportBatch
from app.models.system import User
from app.modules.auth.dependencies import require_permission
from app.modules.ingestion.dbf_catalog import DBF_TABLE_CATALOG
from app.modules.ingestion.dbf_normalizer import normalize_dbf_batch
from app.modules.agent_intelligence.school_context import resolve_school_context
from app.modules.ingestion.dbf_import_service import (
    get_batch,
    get_rows,
    import_dbf_zip,
    list_tables,
)

router = APIRouter()


class DbfNormalizeRequest(BaseModel):
    clear_existing: bool = True
MAX_ZIP_SIZE = 500 * 1024 * 1024


def _batch_payload(batch) -> dict:
    return {
        "batch_id": batch.id,
        "batch_name": batch.batch_name,
        "school_id": batch.school_id,
        "profile_id": batch.profile_id,
        "source_file": batch.source_file,
        "status": batch.status,
        "total_files": batch.total_files,
        "total_records": batch.total_records,
        "file_size": batch.file_size,
        "source_sha256": batch.source_sha256,
        "error_message": batch.error_message,
        "created_at": batch.created_at,
        "finished_at": batch.finished_at,
    }


@router.post("/dbf/imports", status_code=201)
async def create_dbf_import(
    file: UploadFile = File(...),
    batch_name: str | None = Form(default=None),
    school_code: str | None = Form(default=None),
    _user: User = Depends(require_permission("data:import")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    filename = Path(file.filename or "dbf_import.zip").name
    if Path(filename).suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="DBF 文件必须以 zip 压缩包上传")

    content = await file.read()
    if len(content) > MAX_ZIP_SIZE:
        raise HTTPException(status_code=413, detail="压缩包超过 500MB 限制")

    storage_dir = Path(settings.storage_root) / "dbf_imports"
    storage_dir.mkdir(parents=True, exist_ok=True)
    stored_path = storage_dir / f"{uuid4().hex}.zip"
    stored_path.write_bytes(content)

    try:
        school = await resolve_school_context(
            db,
            user_id=_user.id,
            context={"school_code": school_code} if school_code else {},
        )
        batch = await import_dbf_zip(
            db,
            zip_bytes=content,
            source_file=filename,
            batch_name=batch_name,
            school_id=school.get("school_id"),
            profile_id=(school.get("dbf_profile") or {}).get("id"),
        )
    except ValueError as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"DBF 导入失败：{exc}") from exc

    return _batch_payload(batch)


@router.get("/dbf/imports")
async def list_dbf_imports(
    limit: int = Query(default=20, ge=1, le=100),
    _user: User = Depends(require_permission("data:import")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(DbfImportBatch).order_by(DbfImportBatch.created_at.desc()).limit(limit)
    )
    return {"items": [_batch_payload(batch) for batch in result.scalars().all()]}


@router.get("/dbf/schema")
async def dbf_schema(
    _user: User = Depends(require_permission("data:import")),
) -> dict:
    return {"tables": DBF_TABLE_CATALOG}


@router.get("/dbf/imports/{batch_id}")
async def dbf_import_detail(
    batch_id: int,
    _user: User = Depends(require_permission("data:import")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    batch = await get_batch(db, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="DBF 导入批次不存在")
    return {
        **_batch_payload(batch),
        "tables": await list_tables(db, batch_id),
    }


@router.get("/dbf/imports/{batch_id}/tables")
async def dbf_import_tables(
    batch_id: int,
    _user: User = Depends(require_permission("data:import")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if await get_batch(db, batch_id) is None:
        raise HTTPException(status_code=404, detail="DBF 导入批次不存在")
    return {"items": await list_tables(db, batch_id)}


@router.get("/dbf/imports/{batch_id}/tables/{table_name}/rows")
async def dbf_import_rows(
    batch_id: int,
    table_name: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(require_permission("data:import")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if await get_batch(db, batch_id) is None:
        raise HTTPException(status_code=404, detail="DBF 导入批次不存在")
    items = await get_rows(
        db,
        batch_id=batch_id,
        table_name=table_name,
        limit=limit,
        offset=offset,
    )
    sensitive_fields = set(
        DBF_TABLE_CATALOG.get(table_name.lower(), {}).get("sensitive_fields", [])
    )
    if table_name.lower() == "t_tjxx":
        sensitive_fields.update(
            key for item in items for key in item["data"].keys()
        )
    masked_items = []
    for item in items:
        masked_data = {
            key: ("***" if key in sensitive_fields and value not in (None, "") else value)
            for key, value in item["data"].items()
        }
        masked_items.append({"row_no": item["row_no"], "data": masked_data})
    return {
        "items": masked_items,
        "masked_fields": sorted(sensitive_fields),
    }


@router.post("/dbf/imports/{batch_id}/normalize")
async def normalize_dbf_import(
    batch_id: int,
    payload: DbfNormalizeRequest,
    _user: User = Depends(require_permission("data:import")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if await get_batch(db, batch_id) is None:
        raise HTTPException(status_code=404, detail="DBF 导入批次不存在")
    try:
        return await normalize_dbf_batch(
            db,
            batch_id=batch_id,
            clear_existing=payload.clear_existing,
        )
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"DBF 数据归一化失败：{exc}") from exc
