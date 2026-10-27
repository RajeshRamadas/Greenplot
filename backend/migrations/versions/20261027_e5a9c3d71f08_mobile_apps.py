"""mobile apps: push devices, photo previews, indexes

Revision ID: e5a9c3d71f08
Revises: b4d81e6f2a17
Create Date: 2026-10-27 01:43:48.582989

Phones that receive push notifications (device_tokens), a screen-sized copy of large
photos (media.preview_key), and indexes for lookups that were scanning whole tables:
a person's notification feed, an item's photos, and rows found by plot or by person.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

import app.models.base  # noqa: F401 - custom column types


# revision identifiers, used by Alembic.
revision: str = 'e5a9c3d71f08'
down_revision: Union[str, Sequence[str], None] = 'b4d81e6f2a17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('device_tokens',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('tenant_id', sa.Uuid(), nullable=True),
    sa.Column('session_id', sa.Uuid(), nullable=True),
    sa.Column('token', sa.String(length=512), nullable=False),
    sa.Column('platform', sa.String(length=10), nullable=False),
    sa.Column('app_version', sa.String(length=40), nullable=True),
    sa.Column('device_name', sa.String(length=200), nullable=True),
    sa.Column('last_seen_at', app.models.base.UTCDateTime(timezone=True), nullable=True),
    sa.Column('disabled_at', app.models.base.UTCDateTime(timezone=True), nullable=True),
    sa.Column('disabled_reason', sa.String(length=200), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', app.models.base.UTCDateTime(timezone=True), nullable=False),
    sa.Column('updated_at', app.models.base.UTCDateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['refresh_tokens.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token')
    )
    op.create_index(op.f('ix_device_tokens_session_id'), 'device_tokens', ['session_id'], unique=False)
    op.create_index(op.f('ix_device_tokens_tenant_id'), 'device_tokens', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_device_tokens_user_id'), 'device_tokens', ['user_id'], unique=False)
    op.create_index(op.f('ix_assets_property_id'), 'assets', ['property_id'], unique=False)
    op.create_index(op.f('ix_complaints_raised_by'), 'complaints', ['raised_by'], unique=False)
    op.create_index(op.f('ix_incidents_property_id'), 'incidents', ['property_id'], unique=False)
    op.create_index(op.f('ix_incidents_reported_by'), 'incidents', ['reported_by'], unique=False)
    op.create_index(op.f('ix_inspections_inspector_id'), 'inspections', ['inspector_id'], unique=False)
    op.create_index(op.f('ix_maintenance_schedules_property_id'), 'maintenance_schedules', ['property_id'], unique=False)
    op.add_column('media', sa.Column('preview_key', sa.String(length=400), nullable=True))
    op.create_index('ix_media_entity_type_entity_id', 'media', ['entity_type', 'entity_id'], unique=False)
    op.create_index('ix_notifications_user_id_created_at', 'notifications', ['user_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_properties_owner_user_id'), 'properties', ['owner_user_id'], unique=False)
    op.create_index(op.f('ix_sos_alerts_raised_by'), 'sos_alerts', ['raised_by'], unique=False)
    op.create_index(op.f('ix_users_vendor_id'), 'users', ['vendor_id'], unique=False)
    op.create_index(op.f('ix_vehicles_property_id'), 'vehicles', ['property_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_vehicles_property_id'), table_name='vehicles')
    op.drop_index(op.f('ix_users_vendor_id'), table_name='users')
    op.drop_index(op.f('ix_sos_alerts_raised_by'), table_name='sos_alerts')
    op.drop_index(op.f('ix_properties_owner_user_id'), table_name='properties')
    op.drop_index('ix_notifications_user_id_created_at', table_name='notifications')
    op.drop_index('ix_media_entity_type_entity_id', table_name='media')
    op.drop_column('media', 'preview_key')
    op.drop_index(op.f('ix_maintenance_schedules_property_id'), table_name='maintenance_schedules')
    op.drop_index(op.f('ix_inspections_inspector_id'), table_name='inspections')
    op.drop_index(op.f('ix_incidents_reported_by'), table_name='incidents')
    op.drop_index(op.f('ix_incidents_property_id'), table_name='incidents')
    op.drop_index(op.f('ix_complaints_raised_by'), table_name='complaints')
    op.drop_index(op.f('ix_assets_property_id'), table_name='assets')
    op.drop_index(op.f('ix_device_tokens_user_id'), table_name='device_tokens')
    op.drop_index(op.f('ix_device_tokens_tenant_id'), table_name='device_tokens')
    op.drop_index(op.f('ix_device_tokens_session_id'), table_name='device_tokens')
    op.drop_table('device_tokens')
