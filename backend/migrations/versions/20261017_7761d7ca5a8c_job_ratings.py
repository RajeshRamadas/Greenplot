"""job ratings

Revision ID: 7761d7ca5a8c
Revises: 8ee631a554bb
Create Date: 2026-10-17 20:10:46.789196

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.models.base  # noqa: F401 - custom column types


# revision identifiers, used by Alembic.
revision: str = '7761d7ca5a8c'
down_revision: Union[str, Sequence[str], None] = '8ee631a554bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('maintenance_tasks') as batch:
        batch.add_column(sa.Column('rating', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('rating_comment', sa.Text(), nullable=True))
        batch.add_column(sa.Column('rated_at', app.models.base.UTCDateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('rated_by', sa.Uuid(), nullable=True))
        batch.create_foreign_key('fk_maintenance_tasks_rated_by_users', 'users', ['rated_by'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('maintenance_tasks') as batch:
        batch.drop_constraint('fk_maintenance_tasks_rated_by_users', type_='foreignkey')
        batch.drop_column('rated_by')
        batch.drop_column('rated_at')
        batch.drop_column('rating_comment')
        batch.drop_column('rating')
