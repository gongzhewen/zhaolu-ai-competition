import hashlib
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dbf_import import DbfImportBatch, DbfImportRow, DbfImportTable
from app.modules.ingestion.dbf_parser import iter_dbf_from_zip

ROW_CHUNK_SIZE = 1000


async def import_dbf_zip(
    db: AsyncSession,
    *,
    zip_bytes: bytes,
    source_file: str,
    batch_name: str | None = None,
    school_id: int | None = None,
    profile_id: int | None = None,
) -> DbfImportBatch:
    tables = iter_dbf_from_zip(zip_bytes)
    batch = DbfImportBatch(
        batch_name=batch_name or f"DBF导入-{Path(source_file).stem}",
        school_id=school_id,
        profile_id=profile_id,
        source_file=source_file,
        source_sha256=hashlib.sha256(zip_bytes).hexdigest(),
        file_size=len(zip_bytes),
        status="IMPORTING",
        encoding="gb18030",
        metadata_json={"table_count": len(tables), "school_id": school_id, "profile_id": profile_id},
    )
    db.add(batch)
    await db.commit()
    await db.refresh(batch)

    total_records = 0
    try:
        for dbf_table in tables:
            table = DbfImportTable(
                batch_id=batch.id,
                table_name=dbf_table.table_name,
                file_name=dbf_table.file_name,
                record_count=dbf_table.active_record_count,
                field_count=len(dbf_table.fields),
                header_length=dbf_table.header_length,
                record_length=dbf_table.record_length,
                language_driver=dbf_table.language_driver,
                fields=[field.as_dict() for field in dbf_table.fields],
            )
            db.add(table)
            await db.flush()

            for start in range(0, len(dbf_table.rows), ROW_CHUNK_SIZE):
                chunk = dbf_table.rows[start:start + ROW_CHUNK_SIZE]
                db.add_all(
                    [
                        DbfImportRow(
                            batch_id=batch.id,
                            table_id=table.id,
                            row_no=start + index + 1,
                            raw_data=row,
                        )
                        for index, row in enumerate(chunk)
                    ]
                )
                await db.flush()

            total_records += dbf_table.active_record_count
            await db.commit()

        batch.status = "COMPLETED"
        batch.total_files = len(tables)
        batch.total_records = total_records
        batch.finished_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(batch)
        return batch
    except Exception as exc:
        await db.rollback()
        failed = await db.execute(select(DbfImportBatch).where(DbfImportBatch.id == batch.id))
        failed_batch = failed.scalar_one_or_none()
        if failed_batch is not None:
            failed_batch.status = "FAILED"
            failed_batch.error_message = str(exc)
            failed_batch.finished_at = datetime.now(timezone.utc)
            await db.commit()
        raise


async def get_batch(db: AsyncSession, batch_id: int) -> DbfImportBatch | None:
    result = await db.execute(select(DbfImportBatch).where(DbfImportBatch.id == batch_id))
    return result.scalar_one_or_none()


async def list_tables(db: AsyncSession, batch_id: int) -> list[dict]:
    result = await db.execute(
        select(DbfImportTable)
        .where(DbfImportTable.batch_id == batch_id)
        .order_by(DbfImportTable.id)
    )
    return [
        {
            "id": table.id,
            "table_name": table.table_name,
            "file_name": table.file_name,
            "record_count": table.record_count,
            "field_count": table.field_count,
            "fields": table.fields,
        }
        for table in result.scalars().all()
    ]


async def get_rows(
    db: AsyncSession,
    *,
    batch_id: int,
    table_name: str,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    result = await db.execute(
        select(DbfImportRow)
        .join(DbfImportTable, DbfImportRow.table_id == DbfImportTable.id)
        .where(
            DbfImportRow.batch_id == batch_id,
            DbfImportTable.table_name == table_name.lower(),
        )
        .order_by(DbfImportRow.row_no)
        .offset(offset)
        .limit(limit)
    )
    return [
        {"row_no": row.row_no, "data": row.raw_data}
        for row in result.scalars().all()
    ]
