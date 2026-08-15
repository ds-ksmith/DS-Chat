"""drop room_invites (replaced by direct add-to-room)

Revision ID: a3f7c2e91b4d
Revises: 41139ce908df
Create Date: 2026-08-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a3f7c2e91b4d'
down_revision: Union[str, Sequence[str], None] = '41139ce908df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Room invites are replaced by adding an existing user to a room
    # directly (RoomMembership row + notification email, no accept step).
    # The invite_status enum type stays -- site_invites still uses it.
    op.drop_index(op.f('ix_room_invites_token'), table_name='room_invites')
    op.drop_index(op.f('ix_room_invites_target_user_id'), table_name='room_invites')
    op.drop_index(op.f('ix_room_invites_room_id'), table_name='room_invites')
    op.drop_table('room_invites')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table('room_invites',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('room_id', sa.Uuid(), nullable=False),
    sa.Column('invited_by', sa.Uuid(), nullable=False),
    sa.Column('token', sa.String(length=64), nullable=False),
    sa.Column('target_user_id', sa.Uuid(), nullable=True),
    sa.Column('target_email', sa.String(length=255), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', postgresql.ENUM('pending', 'accepted', 'revoked', name='invite_status', create_type=False), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('target_user_id IS NOT NULL OR target_email IS NOT NULL', name='room_invites_target_required'),
    sa.ForeignKeyConstraint(['invited_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ),
    sa.ForeignKeyConstraint(['target_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_room_invites_room_id'), 'room_invites', ['room_id'], unique=False)
    op.create_index(op.f('ix_room_invites_target_user_id'), 'room_invites', ['target_user_id'], unique=False)
    op.create_index(op.f('ix_room_invites_token'), 'room_invites', ['token'], unique=True)
