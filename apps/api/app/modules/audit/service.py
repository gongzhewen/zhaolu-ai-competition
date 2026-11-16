import json

from app.core.text import text
from sqlalchemy.ext.asyncio import AsyncSession


async def write_audit_log(
    db: AsyncSession,
    *,
    user_id: int | None,
    action_type: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    request_data: dict | None = None,
    result_status: str = "SUCCESS",
    ip_address: str | None = None,
) -> None:
    await db.execute(
        text(
            """
            INSERT INTO sys.audit_log (
                user_id, action_type, resource_type, resource_id,
                request_data, result_status, ip_address
            )
            VALUES (
                :user_id, :action_type, :resource_type, :resource_id,
                CAST(:request_data AS jsonb), :result_status, :ip_address
            )
            """
        ),
        {
            "user_id": user_id,
            "action_type": action_type,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "request_data": json.dumps(request_data or {}, ensure_ascii=False, default=str),
            "result_status": result_status,
            "ip_address": ip_address,
        },
    )
    await db.commit()

