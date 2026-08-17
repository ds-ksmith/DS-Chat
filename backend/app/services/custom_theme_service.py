import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CustomTheme, User
from app.schemas.custom_theme import CustomThemeColors

# Sane cap, not a hard product requirement -- keeps the swatch list from
# growing unbounded and matches this app's generally modest per-user scale
# (self-hosted, small groups) elsewhere.
MAX_CUSTOM_THEMES_PER_USER = 20


class CustomThemeNotFoundError(Exception):
    pass


class CustomThemeLimitReachedError(Exception):
    pass


async def list_custom_themes(db: AsyncSession, user_id: uuid.UUID) -> list[CustomTheme]:
    result = await db.execute(
        select(CustomTheme)
        .where(CustomTheme.user_id == user_id)
        .order_by(CustomTheme.created_at)
    )
    return list(result.scalars().all())


async def create_custom_theme(
    db: AsyncSession, user_id: uuid.UUID, name: str, colors: CustomThemeColors
) -> CustomTheme:
    count = await db.scalar(
        select(func.count()).select_from(CustomTheme).where(CustomTheme.user_id == user_id)
    )
    if count >= MAX_CUSTOM_THEMES_PER_USER:
        raise CustomThemeLimitReachedError()

    theme = CustomTheme(user_id=user_id, name=name, colors=colors.model_dump())
    db.add(theme)
    await db.commit()
    await db.refresh(theme)
    return theme


async def _get_owned_theme(db: AsyncSession, user_id: uuid.UUID, theme_id: uuid.UUID) -> CustomTheme:
    theme = await db.get(CustomTheme, theme_id)
    if theme is None or theme.user_id != user_id:
        raise CustomThemeNotFoundError()
    return theme


async def update_custom_theme(
    db: AsyncSession,
    user_id: uuid.UUID,
    theme_id: uuid.UUID,
    name: str | None,
    colors: CustomThemeColors | None,
) -> CustomTheme:
    theme = await _get_owned_theme(db, user_id, theme_id)
    if name is not None:
        theme.name = name
    if colors is not None:
        theme.colors = colors.model_dump()
    await db.commit()
    await db.refresh(theme)
    return theme


async def delete_custom_theme(db: AsyncSession, user_id: uuid.UUID, theme_id: uuid.UUID) -> None:
    theme = await _get_owned_theme(db, user_id, theme_id)
    user = await db.get(User, user_id)
    # A deleted-but-still-active theme would otherwise leave theme='custom'
    # pointing at nothing -- fall back to a preset so the two columns can
    # never disagree about what's actually being displayed.
    if user.active_custom_theme_id == theme.id:
        user.active_custom_theme_id = None
        # Keep the relationship attribute in sync too, not just the raw FK
        # column -- if `user` is already identity-mapped in this session
        # (e.g. a later db.get() in the same request/connection returns the
        # same Python object rather than re-querying), only the FK column
        # being updated would leave .active_custom_theme still pointing at
        # the object we're about to delete below.
        user.active_custom_theme = None
        user.theme = "dark"
        # Flush the FK-clearing UPDATE before the DELETE below -- setting
        # the raw *_id column directly (not the relationship attribute)
        # doesn't register with SQLAlchemy's automatic flush-order
        # dependency detection, so without this the DELETE can be sent
        # first and trip the foreign key constraint.
        await db.flush()
    await db.delete(theme)
    await db.commit()


async def activate_custom_theme(db: AsyncSession, user_id: uuid.UUID, theme_id: uuid.UUID) -> None:
    theme = await _get_owned_theme(db, user_id, theme_id)
    user = await db.get(User, user_id)
    user.theme = "custom"
    user.active_custom_theme_id = theme_id
    # See delete_custom_theme's comment -- keep the relationship attribute
    # in sync too, in case `user` is already identity-mapped elsewhere in
    # this session.
    user.active_custom_theme = theme
    await db.commit()
