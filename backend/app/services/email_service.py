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

    # "Use TLS" means "encrypt this connection", but SMTP has two genuinely
    # different ways to do that, and picking the wrong one breaks the
    # handshake outright rather than just failing to encrypt -- aiosmtplib's
    # own `use_tls` param means *implicit* TLS (encrypted from the first
    # byte, port 465's convention); attempting that against a STARTTLS-only
    # port produces exactly `[SSL: WRONG_VERSION_NUMBER]` (a client TLS
    # ClientHello sent to a server still expecting a plaintext SMTP
    # greeting). So the actual negotiation mode has to be inferred from the
    # port, matching the convention every mail client uses: 465 is implicit
    # TLS, everything else (587, 25, ...) is STARTTLS (plaintext connection,
    # then upgrade). `start_tls=True` (rather than leaving it to
    # aiosmtplib's opportunistic default) makes the requirement strict --
    # if the server doesn't actually support STARTTLS, this fails loudly
    # instead of silently sending in plaintext despite the admin asking for
    # encryption.
    use_implicit_tls = cfg.use_tls and cfg.port == 465
    require_starttls = cfg.use_tls and cfg.port != 465

    await aiosmtplib.send(
        message,
        hostname=cfg.host,
        port=cfg.port,
        username=cfg.username or None,
        password=password,
        use_tls=use_implicit_tls,
        start_tls=require_starttls,
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
