import io
import pathlib
import uuid

from PIL import Image, UnidentifiedImageError

# backend/app/storage.py -> backend/ -> repo root -- same
# resolve-relative-to-file convention FRONTEND_DIST uses in app/main.py, so
# this lands in the right place in both local dev and the /srv/chatapp
# production layout with zero new config.
UPLOADS_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "uploads"

MAX_IMAGE_BYTES = 8 * 1024 * 1024
# Separate named constant (same value for now) so a later size-limit
# redesign for generic file attachments doesn't have to touch image
# behavior.
MAX_FILE_BYTES = MAX_IMAGE_BYTES
_READ_CHUNK_BYTES = 1024 * 1024
_MAX_DIMENSION = 2000

# (storage extension, Pillow format name)
ALLOWED_IMAGE_CONTENT_TYPES: dict[str, tuple[str, str]] = {
    "image/jpeg": (".jpg", "JPEG"),
    "image/png": (".png", "PNG"),
    "image/gif": (".gif", "GIF"),
    "image/webp": (".webp", "WEBP"),
}


class UploadTooLargeError(Exception):
    pass


class InvalidImageError(Exception):
    pass


async def read_capped(file, cap: int = MAX_IMAGE_BYTES) -> bytes:
    """Reads an UploadFile-like object in chunks, raising as soon as `cap`
    is exceeded rather than after buffering the whole (potentially huge)
    body first."""
    chunks = []
    total = 0
    while True:
        chunk = await file.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > cap:
            raise UploadTooLargeError()
        chunks.append(chunk)
    return b"".join(chunks)


def process_image(
    data: bytes,
    content_type: str,
    *,
    square: bool = False,
    max_dimension: int | None = None,
) -> tuple[bytes, str]:
    """Confirms `data` is a genuinely decodable image (not just a spoofed
    Content-Type header) and downscales it so its longer side is
    <=max_dimension (default 2000px) -- except GIF, left untouched so
    animation isn't collapsed to a single frame. When `square` is set
    (avatars), center-crops to the shorter side first. Returns
    (final_bytes, storage_extension)."""
    ext, pillow_format = ALLOWED_IMAGE_CONTENT_TYPES[content_type]
    dimension_cap = max_dimension or _MAX_DIMENSION

    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImageError() from exc

    if content_type == "image/gif":
        return data, ext

    # verify() leaves the image unusable for further processing, so reopen.
    image = Image.open(io.BytesIO(data))
    image.load()
    if pillow_format == "JPEG" and image.mode in ("RGBA", "P"):
        image = image.convert("RGB")
    if square:
        side = min(image.width, image.height)
        left = (image.width - side) // 2
        top = (image.height - side) // 2
        image = image.crop((left, top, left + side, top + side))
    image.thumbnail((dimension_cap, dimension_cap))
    out = io.BytesIO()
    image.save(out, format=pillow_format)
    return out.getvalue(), ext


def save_file(data: bytes, ext: str) -> str:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    storage_filename = f"{uuid.uuid4()}{ext}"
    (UPLOADS_DIR / storage_filename).write_bytes(data)
    return storage_filename


def delete_file(storage_filename: str) -> None:
    """Best-effort delete -- a missing file (already gone, or never
    written) is not an error."""
    (UPLOADS_DIR / storage_filename).unlink(missing_ok=True)
