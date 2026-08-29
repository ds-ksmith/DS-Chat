import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas.custom_emoji import CustomEmojiRead
from app.services.custom_emoji_service import (
    SHORTCODE_PATTERN,
    CustomEmojiNotFoundError,
    DuplicateShortcodeError,
    InvalidShortcodeError,
    NotEmojiOwnerError,
    create_custom_emoji,
    delete_custom_emoji,
    get_custom_emoji_by_shortcode,
    list_custom_emoji,
)
from app.services.upload_settings_service import format_mb, get_upload_settings
from app.storage import (
    ALLOWED_IMAGE_CONTENT_TYPES,
    UPLOADS_DIR,
    InvalidImageError,
    UploadTooLargeError,
    process_image,
    read_capped,
    save_file,
)

# Small and square -- these render inline in message text/reaction pills at
# roughly text size, nowhere near message-image or avatar dimensions.
CUSTOM_EMOJI_MAX_DIMENSION = 128

router = APIRouter(prefix="/api/custom-emoji", tags=["custom-emoji"])


@router.post("", response_model=CustomEmojiRead, status_code=201)
async def upload_custom_emoji_endpoint(
    shortcode: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    shortcode = shortcode.strip().lower()
    # Checked here, before any file processing/saving, so the common
    # rejection cases (bad format, name taken) never leave an orphaned
    # file on disk -- create_custom_emoji below still re-checks both
    # (the actual source of truth, and the only thing that closes the
    # TOCTOU race on the uniqueness check).
    if not SHORTCODE_PATTERN.match(shortcode):
        raise HTTPException(
            status_code=400,
            detail="Shortcode must be 2-30 characters: lowercase letters, numbers, hyphens, underscores",
        )
    if await get_custom_emoji_by_shortcode(db, shortcode) is not None:
        raise HTTPException(status_code=409, detail="An emoji with that shortcode already exists")

    if file.content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported image type")

    upload_settings = await get_upload_settings(db)
    try:
        data = await read_capped(file, cap=upload_settings.max_upload_bytes)
    except UploadTooLargeError:
        raise HTTPException(
            status_code=413,
            detail=f"Image exceeds {format_mb(upload_settings.max_upload_bytes)} limit",
        )

    try:
        data, ext = process_image(
            data, file.content_type, square=True, max_dimension=CUSTOM_EMOJI_MAX_DIMENSION
        )
    except InvalidImageError:
        raise HTTPException(status_code=400, detail="File is not a valid image")

    storage_filename = save_file(data, ext)
    try:
        return await create_custom_emoji(
            db, current_user.id, shortcode, storage_filename, file.content_type
        )
    except (InvalidShortcodeError, DuplicateShortcodeError):
        # Already checked above -- only reachable via the uniqueness
        # check's TOCTOU race (two uploads of the same new shortcode at
        # once), not the common case.
        raise HTTPException(status_code=409, detail="An emoji with that shortcode already exists")


@router.get("", response_model=list[CustomEmojiRead])
async def list_custom_emoji_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_custom_emoji(db)


@router.delete("/{emoji_id}", status_code=204)
async def delete_custom_emoji_endpoint(
    emoji_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await delete_custom_emoji(db, emoji_id, current_user)
    except CustomEmojiNotFoundError:
        raise HTTPException(status_code=404, detail="Custom emoji not found")
    except NotEmojiOwnerError:
        raise HTTPException(status_code=403, detail="Only the uploader or a site admin can remove this")


@router.get("/{shortcode}/image")
async def get_custom_emoji_image_endpoint(
    shortcode: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    emoji = await get_custom_emoji_by_shortcode(db, shortcode)
    if emoji is None:
        raise HTTPException(status_code=404, detail="Custom emoji not found")
    return FileResponse(
        UPLOADS_DIR / emoji.storage_filename,
        media_type=emoji.content_type,
        # #18 follow-up: `max-age=300` (the avatar endpoint's own
        # convention) meant a browser that had already fetched this
        # shortcode's image kept serving it from cache for up to 5 minutes
        # after a delete-and-reupload under the same name swapped in a
        # genuinely different file underneath the same URL -- confirmed
        # live, re-adding an emoji with a just-deleted shortcode showed the
        # old image. `no-cache` (despite the name, still cacheable) forces
        # a revalidation round trip on every use instead of trusting a
        # timed cache -- FileResponse already sets ETag/Last-Modified from
        # the file's own mtime+size (see Starlette's set_stat_headers), so
        # an unchanged file still gets served as a cheap 304 and only an
        # actually-different one (any re-upload) returns fresh bytes.
        headers={"Cache-Control": "private, no-cache"},
    )
