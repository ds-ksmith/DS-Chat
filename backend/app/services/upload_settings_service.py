from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UploadSettings
from app.storage import DEFAULT_MAX_UPLOAD_BYTES


async def get_upload_settings(db: AsyncSession) -> UploadSettings:
    """Unlike SmtpSettings (where "no row yet" means "unconfigured, skip"),
    an upload cap must always resolve to a usable value -- so this creates
    the row with the default on first read instead of returning None."""
    result = await db.execute(select(UploadSettings).limit(1))
    settings_row = result.scalar_one_or_none()
    if settings_row is None:
        settings_row = UploadSettings(max_upload_bytes=DEFAULT_MAX_UPLOAD_BYTES)
        db.add(settings_row)
        await db.commit()
        await db.refresh(settings_row)
    return settings_row


async def update_upload_settings(db: AsyncSession, *, max_upload_bytes: int) -> UploadSettings:
    settings_row = await get_upload_settings(db)
    settings_row.max_upload_bytes = max_upload_bytes
    await db.commit()
    await db.refresh(settings_row)
    return settings_row


def format_mb(num_bytes: int) -> str:
    """Used in 413 error messages, which need to reflect the live
    admin-configured cap rather than a hardcoded "8 MB"."""
    return f"{num_bytes / (1024 * 1024):g} MB"
