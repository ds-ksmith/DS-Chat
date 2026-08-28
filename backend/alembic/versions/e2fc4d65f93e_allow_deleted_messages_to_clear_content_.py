"""allow deleted messages to clear content and attachments

Revision ID: e2fc4d65f93e
Revises: f3f255da9c96
Create Date: 2026-08-28 16:20:02.114630

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2fc4d65f93e'
down_revision: Union[str, Sequence[str], None] = 'f3f255da9c96'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('messages_content_or_attachment_required', 'messages', type_='check')
    op.create_check_constraint(
        'messages_content_or_attachment_required',
        'messages',
        'content IS NOT NULL OR image_id IS NOT NULL OR file_id IS NOT NULL '
        'OR deleted_at IS NOT NULL',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('messages_content_or_attachment_required', 'messages', type_='check')
    op.create_check_constraint(
        'messages_content_or_attachment_required',
        'messages',
        'content IS NOT NULL OR image_id IS NOT NULL OR file_id IS NOT NULL',
    )
