import logging
from email.message import EmailMessage

import aiosmtplib
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import decrypt
from app.models import SmtpSettings
from app.services.smtp_settings_service import get_smtp_settings

logger = logging.getLogger(__name__)


class SmtpNotConfiguredError(Exception):
    pass


async def _deliver(cfg: SmtpSettings, to_address: str, subject: str, body: str) -> None:
    """Raises on failure -- internal helper only. Callers decide whether to
    swallow (send_email) or surface (send_test_email) the error."""
    message = EmailMessage()
    message["From"] = cfg.from_address
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    password = decrypt(cfg.password_encrypted) if cfg.password_encrypted else None
    await aiosmtplib.send(
        message,
        hostname=cfg.host,
        port=cfg.port,
        username=cfg.username or None,
        password=password,
        use_tls=cfg.use_tls,
    )


async def send_email(db: AsyncSession, to_address: str, subject: str, body: str) -> None:
    """Best-effort -- used by invite/notification flows. Never raises: an
    SMTP outage or missing configuration must never block an action (an
    invite, a room membership) that already succeeded in the database."""
    cfg = await get_smtp_settings(db)
    if cfg is None:
        logger.debug("SMTP not configured; skipping email to %s", to_address)
        return
    try:
        await _deliver(cfg, to_address, subject, body)
    except Exception:
        logger.warning("Failed to send email to %s", to_address, exc_info=True)


async def send_test_email(db: AsyncSession, to_address: str) -> None:
    """Used only by the admin 'send test email' button -- raises so the
    admin UI can show why it failed instead of a silent no-op."""
    cfg = await get_smtp_settings(db)
    if cfg is None:
        raise SmtpNotConfiguredError()
    await _deliver(
        cfg,
        to_address,
        "DS Chat test email",
        "This is a test email from DS Chat to confirm your SMTP settings are working.",
    )
