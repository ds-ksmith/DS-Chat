from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import encrypt
from app.models import SmtpSettings


async def get_smtp_settings(db: AsyncSession) -> SmtpSettings | None:
    result = await db.execute(select(SmtpSettings).limit(1))
    return result.scalar_one_or_none()


async def upsert_smtp_settings(
    db: AsyncSession,
    *,
    host: str,
    port: int,
    username: str | None,
    password: str | None,
    from_address: str,
    use_tls: bool,
) -> SmtpSettings:
    settings_row = await get_smtp_settings(db)
    if settings_row is None:
        settings_row = SmtpSettings(
            host=host,
            port=port,
            username=username,
            from_address=from_address,
            use_tls=use_tls,
        )
        db.add(settings_row)
    else:
        settings_row.host = host
        settings_row.port = port
        settings_row.username = username
        settings_row.from_address = from_address
        settings_row.use_tls = use_tls

    # A blank password in the request means "keep the current one" -- the
    # frontend never has the plaintext to send back, only whether one is
    # already set (SmtpSettingsRead.has_password).
    if password:
        settings_row.password_encrypted = encrypt(password)

    await db.commit()
    await db.refresh(settings_row)
    return settings_row
