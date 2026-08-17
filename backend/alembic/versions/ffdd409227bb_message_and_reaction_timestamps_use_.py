"""message and reaction timestamps use clock_timestamp not now

Revision ID: ffdd409227bb
Revises: 05dbe3775e34
Create Date: 2026-08-17 13:40:59.440134

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ffdd409227bb'
down_revision: Union[str, Sequence[str], None] = '05dbe3775e34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Just a catalog default change -- no table rewrite, no lock beyond the
    # instant one ALTER COLUMN SET DEFAULT always takes. Existing rows are
    # untouched; only future inserts pick up clock_timestamp().
    op.alter_column(
        "messages", "created_at", server_default=sa.text("clock_timestamp()")
    )
    op.alter_column(
        "message_reactions", "created_at", server_default=sa.text("clock_timestamp()")
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column("messages", "created_at", server_default=sa.text("now()"))
    op.alter_column("message_reactions", "created_at", server_default=sa.text("now()"))
