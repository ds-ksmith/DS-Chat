import html
import logging
from email.message import EmailMessage

import aiosmtplib
from sqlalchemy.ext.asyncio import AsyncSession

from app.crypto import decrypt
from app.models import CustomTheme, SmtpSettings, User
from app.services.smtp_settings_service import get_smtp_settings

logger = logging.getLogger(__name__)


class SmtpNotConfiguredError(Exception):
    pass


# #68: the 6 tokens actually used by the email template below, out of the
# full ~12-token palette themes.css defines per preset -- an email has no
# equivalent of --ds-surface-2/--ds-void-2/--ds-highlight/--ds-danger, it's
# one card on one background with one accent. Kept in sync by hand with
# frontend/src/styles/tokens.css (the default) and themes.css (the other
# three presets) -- there's no way to share the source of truth across the
# Python/CSS boundary, so if either changes the other needs updating too.
DEFAULT_PALETTE = {
    "void": "#07080f",
    "surface": "#101030",
    "border": "#242478",
    "text": "#fce4fc",
    "muted": "#c0ccd8",
    "accent": "#60d8fc",
}
_PRESET_PALETTES: dict[str, dict[str, str]] = {
    "dark": DEFAULT_PALETTE,
    "light": {
        "void": "#f5f3fb",
        "surface": "#ffffff",
        "border": "#d8d2ee",
        "text": "#1a1030",
        "muted": "#675f80",
        "accent": "#0891b2",
    },
    "midnight": {
        "void": "#000000",
        "surface": "#0a0a14",
        "border": "#262640",
        "text": "#ffffff",
        "muted": "#a8b0c0",
        "accent": "#00f0ff",
    },
    "sunset": {
        "void": "#120a07",
        "surface": "#241408",
        "border": "#4a2c14",
        "text": "#fce8d8",
        "muted": "#c8b0a0",
        "accent": "#fca050",
    },
}


async def _resolve_palette(db: AsyncSession, theme_user: User | None) -> dict[str, str]:
    """#68: an email addressed to an existing user is styled with *their*
    selected theme (mirroring the app itself), not a fixed look -- but
    there's no such thing as "their theme" for someone who doesn't have an
    account yet (site invites), so theme_user is None there and this falls
    back to the default DarkSingularity palette, same as a logged-out page.
    """
    if theme_user is None or theme_user.theme is None:
        return DEFAULT_PALETTE
    if theme_user.theme == "custom":
        if theme_user.active_custom_theme_id is not None:
            # A fresh PK fetch, not `theme_user.active_custom_theme` --
            # that relationship is essentially never eager-loaded by
            # whatever query got this User row in the first place, and
            # touching it lazily here would raise MissingGreenlet in
            # async SQLAlchemy.
            custom = await db.get(CustomTheme, theme_user.active_custom_theme_id)
            if custom is not None:
                colors = custom.colors
                return {key: colors[key] for key in DEFAULT_PALETTE}
        return DEFAULT_PALETTE
    return _PRESET_PALETTES.get(theme_user.theme, DEFAULT_PALETTE)


def _render_text(paragraphs: list[str], cta_label: str | None, cta_url: str | None) -> str:
    body = "\n\n".join(paragraphs)
    if cta_label and cta_url:
        body += f"\n\n{cta_label}: {cta_url}"
    return body


def _render_html(
    palette: dict[str, str],
    subject: str,
    paragraphs: list[str],
    cta_label: str | None,
    cta_url: str | None,
) -> str:
    # Table-based layout with everything inlined -- not the app's own CSS
    # custom properties (email clients strip <style> blocks and don't
    # support :root variables), just their resolved hex values baked in
    # per send. Deliberately plain: one card, one accent color, no imagery
    # that could get blocked by a client's "show images" gate and leave
    # the email looking broken instead of just plain.
    paragraphs_html = "".join(
        f'<p style="margin:0 0 16px;color:{palette["muted"]};font-size:15px;'
        f'line-height:1.6;">{html.escape(p)}</p>'
        for p in paragraphs
    )
    cta_html = ""
    if cta_label and cta_url:
        cta_html = f"""
        <table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0 4px;">
          <tr>
            <td style="border-radius:8px;background:{palette["accent"]};">
              <a href="{html.escape(cta_url)}" style="display:inline-block;padding:12px 22px;
                font-size:15px;font-weight:700;color:{palette["void"]};text-decoration:none;
                border-radius:8px;">{html.escape(cta_label)}</a>
            </td>
          </tr>
        </table>
        """
    return f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:{palette["void"]};">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
      style="background:{palette["void"]};padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" width="480" cellpadding="0" cellspacing="0"
            style="max-width:480px;width:100%;background:{palette["surface"]};
            border:1px solid {palette["border"]};border-radius:12px;padding:32px;
            font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
            <tr>
              <td>
                <div style="font-size:13px;font-weight:800;letter-spacing:0.06em;
                  text-transform:uppercase;color:{palette["accent"]};margin:0 0 20px;">DS Chat</div>
                <h1 style="margin:0 0 16px;font-size:20px;font-weight:800;
                  color:{palette["text"]};">{html.escape(subject)}</h1>
                {paragraphs_html}
                {cta_html}
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


async def _deliver(
    cfg: SmtpSettings, to_address: str, subject: str, html_body: str, text_body: str
) -> None:
    """Raises on failure -- internal helper only. Callers decide whether to
    swallow (send_email) or surface (send_test_email) the error."""
    message = EmailMessage()
    message["From"] = cfg.from_address
    message["To"] = to_address
    message["Subject"] = subject
    # Plain-text part first, HTML as the alternative -- standard
    # multipart/alternative ordering (least to most preferred), so a
    # client with no HTML support (or a spam filter) still gets a normal
    # readable email instead of raw markup.
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

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


async def send_email(
    db: AsyncSession,
    to_address: str,
    subject: str,
    paragraphs: list[str],
    *,
    cta_label: str | None = None,
    cta_url: str | None = None,
    theme_user: User | None = None,
) -> None:
    """Best-effort -- used by invite/notification flows. Never raises: an
    SMTP outage or missing configuration must never block an action (an
    invite, a room membership) that already succeeded in the database.

    `paragraphs` replaces the old flat `body: str` (#68) -- each entry
    renders as its own paragraph in both the HTML and plain-text parts,
    which a single pre-formatted string can't cleanly become HTML from
    without re-parsing it. `theme_user`, when given, styles the email with
    that user's own selected theme (default palette if they haven't picked
    one, or don't have an account at all -- see _resolve_palette).
    """
    cfg = await get_smtp_settings(db)
    if cfg is None:
        # WARNING, not .debug -- this app has no logging config lowering
        # the root level below Python's own WARNING default, so anything
        # below that is silently invisible in production (confirmed live:
        # a real "no emails arriving" report produced nothing in the logs
        # at all, this line included, even though it was relevant).
        logger.warning("SMTP not configured; skipping email to %s", to_address)
        return
    palette = await _resolve_palette(db, theme_user)
    html_body = _render_html(palette, subject, paragraphs, cta_label, cta_url)
    text_body = _render_text(paragraphs, cta_label, cta_url)
    try:
        await _deliver(cfg, to_address, subject, html_body, text_body)
    except Exception:
        logger.warning("Failed to send email to %s", to_address, exc_info=True)


async def send_test_email(db: AsyncSession, to_address: str, theme_user: User | None = None) -> None:
    """Used only by the admin 'send test email' button -- raises so the
    admin UI can show why it failed instead of a silent no-op. theme_user
    is the admin themselves (see routers/admin.py) -- the preview shows
    them their own emails' real look, not a generic default."""
    cfg = await get_smtp_settings(db)
    if cfg is None:
        raise SmtpNotConfiguredError()
    subject = "DS Chat test email"
    paragraphs = ["This is a test email from DS Chat to confirm your SMTP settings are working."]
    palette = await _resolve_palette(db, theme_user)
    html_body = _render_html(palette, subject, paragraphs, None, None)
    text_body = _render_text(paragraphs, None, None)
    await _deliver(cfg, to_address, subject, html_body, text_body)
