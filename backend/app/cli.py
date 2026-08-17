"""Command-line user management.

Public self-registration is disabled (invite-only site), so accounts are
created by an operator running this script directly on the app server.
"""

import argparse
import asyncio
import base64
import getpass

from pydantic import ValidationError

from app.database import async_session_factory
from app.schemas.user import UserCreate
from app.services.auth_service import DuplicateUserError, register_user


def _prompt_password() -> str:
    while True:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password == confirm:
            return password
        print("Passwords didn't match -- try again.")


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


def _generate_vapid_keys() -> None:
    # py_vapid works in DER/PEM internally, but both pywebpush's
    # vapid_private_key argument and the browser's PushManager
    # applicationServerKey expect base64url-encoded *raw* key bytes -- the
    # format used in every Web Push tutorial/example. Encode explicitly
    # rather than relying on py_vapid's own (PEM-oriented) save helpers.
    from py_vapid import Vapid02

    vapid = Vapid02()
    vapid.generate_keys()

    private_raw = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    private_b64 = base64.urlsafe_b64encode(private_raw).decode().rstrip("=")

    from cryptography.hazmat.primitives import serialization

    public_raw = vapid.public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    public_b64 = base64.urlsafe_b64encode(public_raw).decode().rstrip("=")

    print("Add these to backend/.env:")
    print(f"VAPID_PUBLIC_KEY={public_b64}")
    print(f"VAPID_PRIVATE_KEY={private_b64}")
    print("VAPID_SUBJECT=mailto:you@example.com")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_user = subparsers.add_parser("create-user", help="Create a new user account")
    create_user.add_argument("username")
    create_user.add_argument("email")
    create_user.add_argument(
        "password",
        nargs="?",
        default=None,
        help="If omitted, you'll be prompted interactively (hidden input, entered twice to confirm).",
    )
    create_user.add_argument("--admin", action="store_true", help="Grant is_site_admin")

    subparsers.add_parser("generate-vapid-keys", help="Generate a VAPID key pair for push notifications")

    args = parser.parse_args()

    if args.command == "create-user":
        password = args.password if args.password is not None else _prompt_password()
        asyncio.run(_create_user(args.username, args.email, password, args.admin))
    elif args.command == "generate-vapid-keys":
        _generate_vapid_keys()


if __name__ == "__main__":
    main()
