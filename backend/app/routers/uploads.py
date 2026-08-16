from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas.upload_settings import UploadSettingsRead
from app.services.upload_settings_service import get_upload_settings

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.get("/limit", response_model=UploadSettingsRead)
async def get_upload_limit_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Any authenticated user (not just site admins -- unlike
    /api/admin/settings/uploads) can read the current cap, so the composer
    can validate client-side before uploading."""
    cfg = await get_upload_settings(db)
    return UploadSettingsRead(max_upload_bytes=cfg.max_upload_bytes, updated_at=cfg.updated_at)
