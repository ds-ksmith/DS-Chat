"""link previews flag direct image links

Revision ID: f3ec1c1d1992
Revises: d00f93766fa5
Create Date: 2026-08-17 17:56:19.078087

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3ec1c1d1992'
down_revision: Union[str, Sequence[str], None] = 'd00f93766fa5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NOT NULL with a *constant* server_default (unlike a volatile one such
    # as now()/clock_timestamp()) doesn't force a table rewrite in Postgres
    # 11+ -- it's a metadata-only change, safe and instant regardless of
    # table size.
    op.add_column(
        "link_previews",
        sa.Column("is_image", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("link_previews", "is_image")
