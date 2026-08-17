"""named saved custom themes, multiple per user

Revision ID: 8f1b4bf29c5d
Revises: 3c04cf48f4b4
Create Date: 2026-08-17 07:36:18.425662

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8f1b4bf29c5d'
down_revision: Union[str, Sequence[str], None] = '3c04cf48f4b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('custom_themes',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.Column('colors', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_custom_themes_user_id'), 'custom_themes', ['user_id'], unique=False)
    op.add_column('users', sa.Column('active_custom_theme_id', sa.Uuid(), nullable=True))
    # Named explicitly, not left for autogenerate's default -- an unnamed
    # constraint here can't be referenced by name in downgrade() below (a
    # trap this project has hit before on cross-table FKs).
    op.create_foreign_key(
        'users_active_custom_theme_id_fkey', 'users', 'custom_themes',
        ['active_custom_theme_id'], ['id'],
    )

    # Data migration: anyone who already saved colors under the single-
    # theme-per-user shape (#30) gets a real named CustomTheme row instead
    # of losing that data outright when the old column is dropped below.
    op.execute("""
        WITH migrated AS (
            INSERT INTO custom_themes (id, user_id, name, colors, created_at)
            SELECT gen_random_uuid(), id, 'My Theme', custom_theme_colors, now()
            FROM users
            WHERE custom_theme_colors IS NOT NULL
            RETURNING id, user_id
        )
        UPDATE users
        SET active_custom_theme_id = migrated.id
        FROM migrated
        WHERE users.id = migrated.user_id
    """)

    op.drop_column('users', 'custom_theme_colors')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('users', sa.Column('custom_theme_colors', postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=True))

    # Best-effort backfill from whichever theme was active, since that's the
    # one thing worth preserving going backward -- any *other* saved themes
    # are still genuinely lost on downgrade (the old column only ever held
    # one palette per user).
    op.execute("""
        UPDATE users
        SET custom_theme_colors = custom_themes.colors
        FROM custom_themes
        WHERE users.active_custom_theme_id = custom_themes.id
    """)

    op.drop_constraint('users_active_custom_theme_id_fkey', 'users', type_='foreignkey')
    op.drop_column('users', 'active_custom_theme_id')
    op.drop_index(op.f('ix_custom_themes_user_id'), table_name='custom_themes')
    op.drop_table('custom_themes')
