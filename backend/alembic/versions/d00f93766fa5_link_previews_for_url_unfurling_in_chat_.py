"""link previews for URL unfurling in chat messages

Revision ID: d00f93766fa5
Revises: ffdd409227bb
Create Date: 2026-08-17 17:31:13.598917

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd00f93766fa5'
down_revision: Union[str, Sequence[str], None] = 'ffdd409227bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "link_previews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("image_url", sa.String(length=2048), nullable=True),
        sa.Column("site_name", sa.String(length=200), nullable=True),
        sa.Column("fetch_failed", sa.Boolean(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_link_previews_url"), "link_previews", ["url"], unique=True
    )
    # Nullable, no default -- just adds a column to the catalog, no table
    # rewrite, no lock beyond the instant one ALTER TABLE ADD COLUMN always
    # takes for a nullable column with no default.
    op.add_column("messages", sa.Column("preview_url", sa.String(length=2048), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("messages", "preview_url")
    op.drop_index(op.f("ix_link_previews_url"), table_name="link_previews")
    op.drop_table("link_previews")
