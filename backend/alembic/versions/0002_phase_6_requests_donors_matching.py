"""phase 6 requests donors matching

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-03 13:35:49.602698
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

ENUMS = {
    'abo_group': ('O', 'A', 'B', 'AB',),
    'rh_factor': ('pos', 'neg',),
    'component': ('red_cells', 'platelets', 'plasma',),
    'urgency': ('emergency', 'urgent', 'routine',),
    'request_status': ('submitted', 'confirmed', 'covered_by_stock', 'matching', 'fulfilled', 'partially_fulfilled', 'unfilled', 'cancelled',),
    'availability': ('available', 'unavailable', 'travelling',),
    'match_status': ('invited', 'accepted', 'declined', 'expired', 'donated', 'no_show', 'deferred_on_site', 'withdrawn',),
}
NEW_ENUMS = ['availability', 'match_status', 'request_status', 'urgency']  # the others exist since 0001


def E(name: str) -> sa.types.TypeEngine:
    return sa.Enum(*ENUMS[name], name=name).with_variant(postgresql.ENUM(*ENUMS[name], name=name, create_type=False), "postgresql")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for name in NEW_ENUMS:
            postgresql.ENUM(*ENUMS[name], name=name).create(bind, checkfirst=True)
    op.create_table('blood_request',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('requester_id', sa.Uuid(), nullable=False),
    sa.Column('site_id', sa.Uuid(), nullable=False),
    sa.Column('abo', E('abo_group'), nullable=False),
    sa.Column('rh', E('rh_factor'), nullable=False),
    sa.Column('component', E('component'), nullable=False),
    sa.Column('units_needed', sa.Integer(), nullable=False),
    sa.Column('units_secured', sa.Integer(), nullable=False),
    sa.Column('urgency', E('urgency'), nullable=False),
    sa.Column('needed_by', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', E('request_status'), nullable=False),
    sa.Column('confirmed_by', sa.Uuid(), nullable=True),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('stock_units', sa.Integer(), nullable=False),
    sa.Column('shortfall', sa.Integer(), nullable=False),
    sa.Column('wave', sa.Integer(), nullable=False),
    sa.Column('next_wave_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('escalated_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('units_needed BETWEEN 1 AND 20', name='request_units_range'),
    sa.ForeignKeyConstraint(['confirmed_by'], ['app_user.id'], ),
    sa.ForeignKeyConstraint(['requester_id'], ['app_user.id'], ),
    sa.ForeignKeyConstraint(['site_id'], ['site.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('blood_request', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_blood_request_requester_id'), ['requester_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_blood_request_site_id'), ['site_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_blood_request_status'), ['status'], unique=False)

    op.create_table('donor',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('abo', E('abo_group'), nullable=True),
    sa.Column('rh', E('rh_factor'), nullable=True),
    sa.Column('group_verified', sa.Boolean(), nullable=False),
    sa.Column('area_lat', sa.Float(), nullable=True),
    sa.Column('area_lng', sa.Float(), nullable=True),
    sa.Column('birth_year', sa.Integer(), nullable=True),
    sa.Column('sex', sa.String(), nullable=True),
    sa.Column('weight_ok', sa.Boolean(), nullable=True),
    sa.Column('last_donation_on', sa.Date(), nullable=True),
    sa.Column('availability', E('availability'), nullable=False),
    sa.Column('quiet_start', sa.Time(), nullable=True),
    sa.Column('quiet_end', sa.Time(), nullable=True),
    sa.Column('emergency_override', sa.Boolean(), nullable=False),
    sa.Column('max_invites_30d', sa.Integer(), nullable=False),
    sa.Column('reliability', sa.Numeric(precision=4, scale=3), nullable=False),
    sa.Column('consent_version', sa.String(), nullable=False),
    sa.Column('consent_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reminded_for', sa.Date(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['app_user.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    op.create_table('notification',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('channel', sa.String(), nullable=False),
    sa.Column('template', sa.String(), nullable=False),
    sa.Column('payload', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['app_user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('notification', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_notification_user_id'), ['user_id'], unique=False)

    op.create_table('deferral',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('donor_id', sa.Uuid(), nullable=False),
    sa.Column('category', sa.String(), nullable=False),
    sa.Column('eligible_again_on', sa.Date(), nullable=False),
    sa.Column('recorded_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['donor_id'], ['donor.id'], ),
    sa.ForeignKeyConstraint(['recorded_by'], ['app_user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('deferral', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_deferral_donor_id'), ['donor_id'], unique=False)

    op.create_table('donor_match',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('request_id', sa.Uuid(), nullable=False),
    sa.Column('donor_id', sa.Uuid(), nullable=False),
    sa.Column('wave', sa.Integer(), nullable=False),
    sa.Column('score', sa.Numeric(precision=5, scale=4), nullable=False),
    sa.Column('status', E('match_status'), nullable=False),
    sa.Column('invited_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('outcome_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['donor_id'], ['donor.id'], ),
    sa.ForeignKeyConstraint(['request_id'], ['blood_request.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('request_id', 'donor_id', name='match_once_per_request')
    )
    with op.batch_alter_table('donor_match', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_donor_match_donor_id'), ['donor_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_donor_match_request_id'), ['request_id'], unique=False)

    op.create_table('message_thread',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('match_id', sa.Uuid(), nullable=False),
    sa.Column('donor_shares_phone', sa.Boolean(), nullable=False),
    sa.Column('requester_shares_phone', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['match_id'], ['donor_match.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('match_id')
    )
    op.create_table('message',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('thread_id', sa.Uuid(), nullable=False),
    sa.Column('sender_id', sa.Uuid(), nullable=False),
    sa.Column('body', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('length(body) <= 1000', name='message_length'),
    sa.ForeignKeyConstraint(['sender_id'], ['app_user.id'], ),
    sa.ForeignKeyConstraint(['thread_id'], ['message_thread.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('message', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_message_thread_id'), ['thread_id'], unique=False)

    with op.batch_alter_table('site', schema=None) as batch_op:
        batch_op.add_column(sa.Column('area', sa.String(), nullable=True))

    if bind.dialect.name == "postgresql":  # new tables need the runtime grants too
        op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lifegrid_app') THEN "
                   "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO lifegrid_app; "
                   "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO lifegrid_app; "
                   "REVOKE UPDATE, DELETE ON audit_event FROM lifegrid_app; END IF; END $$;")


def downgrade() -> None:
    with op.batch_alter_table('site', schema=None) as batch_op:
        batch_op.drop_column('area')

    with op.batch_alter_table('message', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_message_thread_id'))

    op.drop_table('message')
    op.drop_table('message_thread')
    with op.batch_alter_table('donor_match', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_donor_match_request_id'))
        batch_op.drop_index(batch_op.f('ix_donor_match_donor_id'))

    op.drop_table('donor_match')
    with op.batch_alter_table('deferral', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_deferral_donor_id'))

    op.drop_table('deferral')
    with op.batch_alter_table('notification', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_notification_user_id'))

    op.drop_table('notification')
    op.drop_table('donor')
    with op.batch_alter_table('blood_request', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_blood_request_status'))
        batch_op.drop_index(batch_op.f('ix_blood_request_site_id'))
        batch_op.drop_index(batch_op.f('ix_blood_request_requester_id'))

    op.drop_table('blood_request')
    if op.get_bind().dialect.name == "postgresql":
        for name in NEW_ENUMS:
            postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
