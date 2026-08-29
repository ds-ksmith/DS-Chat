import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import InviteStatus, SiteInvite, User
from app.models.site_invite import DEFAULT_SITE_INVITE_LIFETIME
from app.schemas.user import UserCreate
from app.security import hash_token
from app.services.audit import record_audit_log
from app.services.auth_service import register_user
from app.services.email_service import send_email


class SiteInviteNotFoundError(Exception):
    pass


class SiteInviteNotPendingError(Exception):
    pass


class SiteInviteInvalidError(Exception):
    pass


async def _send_invite_email(db: AsyncSession, inviter_username: str, base_url: str, email: str, raw_token: str) -> None:
    signup_link = f"{base_url.rstrip('/')}/signup?token={raw_token}"
    # No theme_user -- the invitee doesn't have an account yet, so there's
    # no theme of theirs to use (#68). Default palette, same as any
    # logged-out page.
    await send_email(
        db,
        email,
        "You're invited to join DS Chat",
        [
            f"You've been invited to join DS Chat by {inviter_username}.",
            "This link expires in 7 days.",
        ],
        cta_label="Set up your account",
        cta_url=signup_link,
    )


async def create_site_invite(
    db: AsyncSession, actor: User, base_url: str, email: str
) -> SiteInvite:
    raw_token = secrets.token_urlsafe(32)
    invite_id = uuid.uuid4()
    invite = SiteInvite(
        id=invite_id, email=email, invited_by=actor.id, token_hash=hash_token(raw_token)
    )
    db.add(invite)
    record_audit_log(db, actor, "user.invite", "invite", invite_id, {"email": email})
    await db.commit()
    await db.refresh(invite)

    await _send_invite_email(db, actor.username, base_url, email, raw_token)
    return invite


async def list_site_invites(db: AsyncSession) -> list[SiteInvite]:
    # Pending only (#61) -- the admin UI's only consumer of this list labels
    # it "Pending invites" and had no way to drop a row once it was accepted
    # or revoked, since the backend returned every invite ever sent forever.
    # An accepted/revoked invite has nothing further to act on here; its
    # history already lives in the audit log ("user.invite"/"invite.revoke").
    result = await db.execute(
        select(SiteInvite)
        .where(SiteInvite.status == InviteStatus.pending)
        .options(selectinload(SiteInvite.inviter))
        .order_by(SiteInvite.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_site_invite(db: AsyncSession, actor: User, invite_id: uuid.UUID) -> SiteInvite:
    invite = await db.get(SiteInvite, invite_id)
    if invite is None:
        raise SiteInviteNotFoundError()
    if invite.status != InviteStatus.pending:
        raise SiteInviteNotPendingError()

    invite.status = InviteStatus.revoked
    record_audit_log(db, actor, "invite.revoke", "invite", invite.id)
    await db.commit()
    await db.refresh(invite)
    return invite


async def resend_site_invite(
    db: AsyncSession, actor: User, base_url: str, invite_id: uuid.UUID
) -> SiteInvite:
    invite = await db.get(SiteInvite, invite_id)
    if invite is None:
        raise SiteInviteNotFoundError()
    if invite.status != InviteStatus.pending:
        raise SiteInviteNotPendingError()

    # A fresh token and a reset 7-day expiry, not just re-sending the same
    # link -- the old link stops working the moment this runs (same
    # "rotate, don't just repeat" instinct as a password-reset resend), and
    # it means resending something close to expiring actually buys the
    # full week again instead of whatever was left.
    raw_token = secrets.token_urlsafe(32)
    invite.token_hash = hash_token(raw_token)
    invite.expires_at = datetime.now(timezone.utc) + DEFAULT_SITE_INVITE_LIFETIME
    record_audit_log(db, actor, "invite.resend", "invite", invite.id, {"email": invite.email})
    await db.commit()
    await db.refresh(invite)

    await _send_invite_email(db, actor.username, base_url, invite.email, raw_token)
    return invite


async def _get_pending_invite_by_token(db: AsyncSession, token: str) -> SiteInvite:
    result = await db.execute(
        select(SiteInvite).where(SiteInvite.token_hash == hash_token(token))
    )
    invite = result.scalar_one_or_none()
    if invite is None or invite.status != InviteStatus.pending:
        raise SiteInviteInvalidError()
    if invite.expires_at <= datetime.now(timezone.utc):
        raise SiteInviteInvalidError()
    return invite


async def validate_signup_token(db: AsyncSession, token: str) -> SiteInvite:
    return await _get_pending_invite_by_token(db, token)


async def complete_signup(db: AsyncSession, token: str, username: str, password: str) -> User:
    invite = await _get_pending_invite_by_token(db, token)

    user = await register_user(
        db, UserCreate(username=username, email=invite.email, password=password)
    )

    invite.status = InviteStatus.accepted
    await db.commit()
    return user
