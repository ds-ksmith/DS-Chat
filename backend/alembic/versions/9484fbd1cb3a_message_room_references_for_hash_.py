"""message room references for hash roomname links

Revision ID: 9484fbd1cb3a
Revises: f3ec1c1d1992
Create Date: 2026-08-17 18:57:16.584680

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9484fbd1cb3a'
down_revision: Union[str, Sequence[str], None] = 'f3ec1c1d1992'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "message_room_references",
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"]),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"]),
        sa.PrimaryKeyConstraint("message_id", "room_id"),
    )
    op.create_index(
        op.f("ix_message_room_references_room_id"),
        "message_room_references",
        ["room_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_message_room_references_room_id"), table_name="message_room_references"
    )
    op.drop_table("message_room_references")
