"""separate WhatsApp numbers for customers

Revision ID: 5a1d0e7c9b42
Revises: 8fe8bf48a1f0
Create Date: 2026-10-26 04:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a1d0e7c9b42'
down_revision: Union[str, Sequence[str], None] = '8fe8bf48a1f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column): a NULL WhatsApp number means "same as the calling number"
COLUMNS = [
    ("users", "whatsapp_phone"),
    ("residents", "whatsapp_phone"),
    ("properties", "owner_whatsapp"),
    ("tickets", "contact_whatsapp"),
    ("signup_requests", "whatsapp_phone"),
]


def upgrade() -> None:
    for table, column in COLUMNS:
        op.add_column(table, sa.Column(column, sa.String(length=30), nullable=True))


def downgrade() -> None:
    for table, column in reversed(COLUMNS):
        op.drop_column(table, column)
