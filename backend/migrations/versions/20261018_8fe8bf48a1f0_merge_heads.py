"""merge job ratings, subscriptions and owner updates

Revision ID: 8fe8bf48a1f0
Revises: 7761d7ca5a8c, cb63faa34d4f, dda5126a8e54
Create Date: 2026-10-18 04:31:36.700548

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.models.base  # noqa: F401 - custom column types


# revision identifiers, used by Alembic.
revision: str = '8fe8bf48a1f0'
down_revision: Union[str, Sequence[str], None] = ('7761d7ca5a8c', 'cb63faa34d4f', 'dda5126a8e54')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
