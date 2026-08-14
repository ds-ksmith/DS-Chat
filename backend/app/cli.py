"""Command-line user management.

Public self-registration is disabled (invite-only site), so accounts are
created by an operator running this script directly on the app server.
"""

import argparse
import asyncio

from pydantic import ValidationError

from app.database import async_session_factory
from app.schemas.user import UserCreate
from app.services.auth_service import DuplicateUserError, register_user


async def _create_user(username: str, email: str, password: str, is_admin: bool) -> None:
    try:
        data = UserCreate(username=username, email=email, password=password)
    except ValidationError as exc:
        raise SystemExit(str(exc))

    async with async_session_factory() as db:
        try:
            user = await register_user(db, data)
        except DuplicateUserError:
            raise SystemExit(f"Username or email already taken: {username} / {email}")

        if is_admin:
            user.is_site_admin = True
            await db.commit()

    print(f"Created user {username!r} (id={user.id}, admin={is_admin})")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_user = subparsers.add_parser("create-user", help="Create a new user account")
    create_user.add_argument("username")
    create_user.add_argument("email")
    create_user.add_argument("password")
    create_user.add_argument("--admin", action="store_true", help="Grant is_site_admin")

    args = parser.parse_args()

    if args.command == "create-user":
        asyncio.run(_create_user(args.username, args.email, args.password, args.admin))


if __name__ == "__main__":
    main()
