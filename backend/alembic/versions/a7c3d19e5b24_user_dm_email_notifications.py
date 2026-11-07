"""user dm_email_notifications

Revision ID: a7c3d19e5b24
Revises: e81c9bcc82b9
Create Date: 2026-11-06 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c3d19e5b24'
down_revision: Union[str, Sequence[str], None] = 'e81c9bcc82b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default='true' so every existing user keeps getting DM emails,
    # which is how it behaved before this was a setting. A constant default
    # is a metadata-only change in Postgres 11+, not a table rewrite.
    op.add_column('users', sa.Column('dm_email_notifications', sa.Boolean(), server_default='true', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'dm_email_notifications')
