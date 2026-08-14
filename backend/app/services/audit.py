import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import AdminAuditLog, User


def record_audit_log(
    db: AsyncSession,
    actor: User,
    action: str,
    target_type: str,
    target_id: uuid.UUID,
    metadata: dict | None = None,
) -> None:
    db.add(
        AdminAuditLog(
            actor_id=actor.id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            metadata_=metadata,
        )
    )


async def list_audit_log(
    db: AsyncSession, limit: int = 50, offset: int = 0
) -> list[AdminAuditLog]:
    result = await db.execute(
        select(AdminAuditLog)
        .options(selectinload(AdminAuditLog.actor))
        .order_by(AdminAuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())
