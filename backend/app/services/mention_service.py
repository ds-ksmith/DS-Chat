import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RoomMembership, User

MENTION_PATTERN = re.compile(r"@([a-zA-Z0-9_.-]+)")


def strip_code_spans(content: str) -> str:
    """Blanks out fenced code blocks and inline code spans (replacing with
    equal-length whitespace, so a bare '@'/'#' in pasted code -- a
    decorator, an email fragment, a shell comment -- doesn't trigger a
    mention or room reference. Mirrors the same skip logic
    frontend/src/components/MessageContent.tsx already uses for emoji
    shortcode conversion. Shared with room_reference_service, not private
    to this module anymore."""
    lines = content.split("\n")
    in_fence = False
    out = []
    for line in lines:
        if re.match(r"^\s*```", line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        parts = re.split(r"(`+[^`]*`+)", line)
        out.append("".join(part if i % 2 == 0 else " " * len(part) for i, part in enumerate(parts)))
    return "\n".join(out)


async def extract_mentioned_user_ids(
    db: AsyncSession, room_id: uuid.UUID, content: str
) -> set[uuid.UUID]:
    """Resolves `@username` tokens in `content` against this room's actual
    members -- a bare '@' followed by prose that happens to not match
    anyone's username is just text, not a mention."""
    usernames = set(MENTION_PATTERN.findall(strip_code_spans(content)))
    if not usernames:
        return set()

    result = await db.execute(
        select(RoomMembership.user_id)
        .join(User, User.id == RoomMembership.user_id)
        .where(RoomMembership.room_id == room_id, User.username.in_(usernames))
    )
    return {row[0] for row in result.all()}
