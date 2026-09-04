from app.services.system_user_service import SYSTEM_USERNAME, get_or_create_system_user


async def test_get_or_create_system_user_creates_bot_account(db_session):
    user = await get_or_create_system_user(db_session)
    assert user.username == SYSTEM_USERNAME
    assert user.is_bot is True


async def test_get_or_create_system_user_is_idempotent(db_session):
    first = await get_or_create_system_user(db_session)
    second = await get_or_create_system_user(db_session)
    assert first.id == second.id
