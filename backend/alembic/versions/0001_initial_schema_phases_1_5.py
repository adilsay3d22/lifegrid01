"""initial schema phases 1-5

Revision ID: 0001
Revises: 
Create Date: 2026-10-03 12:12:50.354092
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

ENUMS = {
    'user_role': ('bank_manager', 'hospital_lead', 'donor_coordinator', 'donor', 'requester', 'admin', 'auditor',),
    'component': ('red_cells', 'platelets', 'plasma',),
    'abo_group': ('O', 'A', 'B', 'AB',),
    'rh_factor': ('pos', 'neg',),
    'site_type': ('hospital', 'blood_bank',),
    'unit_status': ('available', 'reserved', 'in_transit', 'quarantined', 'issued', 'expired', 'discarded',),
}


def E(name: str) -> sa.types.TypeEngine:
    """Shared PostgreSQL enum types are created once up front, so columns must not create them again."""
    return sa.Enum(*ENUMS[name], name=name).with_variant(postgresql.ENUM(*ENUMS[name], name=name, create_type=False), "postgresql")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for name, values in ENUMS.items():
            postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)
    op.create_table('app_user',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('role', E('user_role'), nullable=False),
    sa.Column('email', sa.String(), nullable=True),
    sa.Column('password_hash', sa.String(), nullable=True),
    sa.Column('totp_secret_enc', sa.LargeBinary(), nullable=True),
    sa.Column('phone_enc', sa.LargeBinary(), nullable=True),
    sa.Column('phone_hash', sa.String(), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('email IS NOT NULL OR phone_hash IS NOT NULL', name='user_has_login'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email'),
    sa.UniqueConstraint('phone_hash')
    )
    op.create_table('audit_event',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('actor_user_id', sa.Uuid(), nullable=True),
    sa.Column('action', sa.String(), nullable=False),
    sa.Column('entity_type', sa.String(), nullable=False),
    sa.Column('entity_id', sa.String(), nullable=False),
    sa.Column('data', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('prev_hash', sa.LargeBinary(), nullable=False),
    sa.Column('hash', sa.LargeBinary(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('compat_rule',
    sa.Column('component', E('component'), nullable=False),
    sa.Column('recipient_abo', E('abo_group'), nullable=False),
    sa.Column('recipient_rh', E('rh_factor'), nullable=False),
    sa.Column('donor_abo', E('abo_group'), nullable=False),
    sa.Column('donor_rh', E('rh_factor'), nullable=False),
    sa.Column('rank', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('component', 'recipient_abo', 'recipient_rh', 'donor_abo', 'donor_rh')
    )
    op.create_table('otp_challenge',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('phone_hash', sa.String(), nullable=False),
    sa.Column('code_hash', sa.String(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('otp_challenge', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_otp_challenge_phone_hash'), ['phone_hash'], unique=False)

    op.create_table('site',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('code', sa.String(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('type', E('site_type'), nullable=False),
    sa.Column('lat', sa.Float(), nullable=False),
    sa.Column('lng', sa.Float(), nullable=False),
    sa.Column('timezone', sa.String(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_table('transfer_plan',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('horizon_days', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('solver_status', sa.String(), nullable=False),
    sa.Column('solver_seconds', sa.Numeric(precision=8, scale=2), nullable=True),
    sa.Column('is_fallback', sa.Boolean(), nullable=False),
    sa.Column('projected', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('blood_unit',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('unit_code', sa.String(), nullable=False),
    sa.Column('abo', E('abo_group'), nullable=False),
    sa.Column('rh', E('rh_factor'), nullable=False),
    sa.Column('component', E('component'), nullable=False),
    sa.Column('collected_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('site_id', sa.Uuid(), nullable=False),
    sa.Column('status', E('unit_status'), nullable=False),
    sa.Column('reserved_for', sa.Uuid(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("(status = 'reserved') = (reserved_for IS NOT NULL)", name='reserved_has_request'),
    sa.CheckConstraint('expires_at > collected_at', name='expiry_after_collection'),
    sa.ForeignKeyConstraint(['site_id'], ['site.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('unit_code')
    )
    with op.batch_alter_table('blood_unit', schema=None) as batch_op:
        batch_op.create_index('ix_unit_pick', ['site_id', 'component', 'abo', 'rh', 'status', 'expires_at'], unique=False)

    op.create_table('forecast',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('run_id', sa.Uuid(), nullable=False),
    sa.Column('site_id', sa.Uuid(), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('component', E('component'), nullable=False),
    sa.Column('abo', E('abo_group'), nullable=False),
    sa.Column('rh', E('rh_factor'), nullable=False),
    sa.Column('point', sa.Numeric(precision=8, scale=2), nullable=False),
    sa.Column('low', sa.Numeric(precision=8, scale=2), nullable=False),
    sa.Column('high', sa.Numeric(precision=8, scale=2), nullable=False),
    sa.Column('model', sa.String(), nullable=False),
    sa.Column('model_version', sa.String(), nullable=False),
    sa.Column('backtest_mae', sa.Numeric(precision=8, scale=3), nullable=False),
    sa.Column('baseline_mae', sa.Numeric(precision=8, scale=3), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('low <= point AND point <= high', name='forecast_band_order'),
    sa.ForeignKeyConstraint(['site_id'], ['site.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('forecast', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_forecast_run_id'), ['run_id'], unique=False)
        batch_op.create_index('ix_forecast_series', ['site_id', 'component', 'abo', 'rh', 'day'], unique=False)

    op.create_table('refresh_token',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('family_id', sa.Uuid(), nullable=False),
    sa.Column('token_hash', sa.String(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['app_user.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    with op.batch_alter_table('refresh_token', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_refresh_token_family_id'), ['family_id'], unique=False)

    op.create_table('setting',
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('value', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['updated_by'], ['app_user.id'], ),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('setting_history',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('old_value', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('new_value', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('changed_by', sa.Uuid(), nullable=True),
    sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['changed_by'], ['app_user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('transfer',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('recommendation_id', sa.Uuid(), nullable=True),
    sa.Column('from_site_id', sa.Uuid(), nullable=False),
    sa.Column('to_site_id', sa.Uuid(), nullable=False),
    sa.Column('component', E('component'), nullable=False),
    sa.Column('abo', E('abo_group'), nullable=False),
    sa.Column('rh', E('rh_factor'), nullable=False),
    sa.Column('units', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('dispatched_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('from_site_id <> to_site_id', name='transfer_distinct_sites'),
    sa.ForeignKeyConstraint(['from_site_id'], ['site.id'], ),
    sa.ForeignKeyConstraint(['to_site_id'], ['site.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('transfer_recommendation',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('plan_id', sa.Uuid(), nullable=False),
    sa.Column('from_site_id', sa.Uuid(), nullable=False),
    sa.Column('to_site_id', sa.Uuid(), nullable=False),
    sa.Column('component', E('component'), nullable=False),
    sa.Column('abo', E('abo_group'), nullable=False),
    sa.Column('rh', E('rh_factor'), nullable=False),
    sa.Column('units', sa.Integer(), nullable=False),
    sa.Column('reason', sa.String(), nullable=False),
    sa.Column('expected_benefit', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('decided_by', sa.Uuid(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('units > 0', name='rec_units_positive'),
    sa.ForeignKeyConstraint(['decided_by'], ['app_user.id'], ),
    sa.ForeignKeyConstraint(['from_site_id'], ['site.id'], ),
    sa.ForeignKeyConstraint(['plan_id'], ['transfer_plan.id'], ),
    sa.ForeignKeyConstraint(['to_site_id'], ['site.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('transfer_recommendation', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_transfer_recommendation_plan_id'), ['plan_id'], unique=False)

    op.create_table('usage_daily',
    sa.Column('site_id', sa.Uuid(), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('component', E('component'), nullable=False),
    sa.Column('abo', E('abo_group'), nullable=False),
    sa.Column('rh', E('rh_factor'), nullable=False),
    sa.Column('units_used', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['site_id'], ['site.id'], ),
    sa.PrimaryKeyConstraint('site_id', 'day', 'component', 'abo', 'rh')
    )
    op.create_table('user_site',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('site_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['site_id'], ['site.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['app_user.id'], ),
    sa.PrimaryKeyConstraint('user_id', 'site_id')
    )
    op.create_table('temperature_excursion',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('site_id', sa.Uuid(), nullable=True),
    sa.Column('transfer_id', sa.Uuid(), nullable=True),
    sa.Column('component', E('component'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('min_c', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('max_c', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.Column('recorded_by', sa.Uuid(), nullable=True),
    sa.ForeignKeyConstraint(['recorded_by'], ['app_user.id'], ),
    sa.ForeignKeyConstraint(['site_id'], ['site.id'], ),
    sa.ForeignKeyConstraint(['transfer_id'], ['transfer.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('unit_movement',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('unit_id', sa.Uuid(), nullable=False),
    sa.Column('from_status', E('unit_status'), nullable=True),
    sa.Column('to_status', E('unit_status'), nullable=False),
    sa.Column('from_site_id', sa.Uuid(), nullable=True),
    sa.Column('to_site_id', sa.Uuid(), nullable=True),
    sa.Column('transfer_id', sa.Uuid(), nullable=True),
    sa.Column('actor_user_id', sa.Uuid(), nullable=True),
    sa.Column('reason', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['app_user.id'], ),
    sa.ForeignKeyConstraint(['from_site_id'], ['site.id'], ),
    sa.ForeignKeyConstraint(['to_site_id'], ['site.id'], ),
    sa.ForeignKeyConstraint(['transfer_id'], ['transfer.id'], ),
    sa.ForeignKeyConstraint(['unit_id'], ['blood_unit.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('unit_movement', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_unit_movement_transfer_id'), ['transfer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_unit_movement_unit_id'), ['unit_id'], unique=False)

    if bind.dialect.name == "postgresql":
        # Runtime role: read/write everything except the audit log, which is insert + read only (spec section 11).
        op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lifegrid_app') THEN "
                   "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO lifegrid_app; "
                   "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO lifegrid_app; "
                   "REVOKE UPDATE, DELETE ON audit_event FROM lifegrid_app; END IF; END $$;")


def downgrade() -> None:
    with op.batch_alter_table('unit_movement', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_unit_movement_unit_id'))
        batch_op.drop_index(batch_op.f('ix_unit_movement_transfer_id'))

    op.drop_table('unit_movement')
    op.drop_table('temperature_excursion')
    op.drop_table('user_site')
    op.drop_table('usage_daily')
    with op.batch_alter_table('transfer_recommendation', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_transfer_recommendation_plan_id'))

    op.drop_table('transfer_recommendation')
    op.drop_table('transfer')
    op.drop_table('setting_history')
    op.drop_table('setting')
    with op.batch_alter_table('refresh_token', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_refresh_token_family_id'))

    op.drop_table('refresh_token')
    with op.batch_alter_table('forecast', schema=None) as batch_op:
        batch_op.drop_index('ix_forecast_series')
        batch_op.drop_index(batch_op.f('ix_forecast_run_id'))

    op.drop_table('forecast')
    with op.batch_alter_table('blood_unit', schema=None) as batch_op:
        batch_op.drop_index('ix_unit_pick')

    op.drop_table('blood_unit')
    op.drop_table('transfer_plan')
    op.drop_table('site')
    with op.batch_alter_table('otp_challenge', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_otp_challenge_phone_hash'))

    op.drop_table('otp_challenge')
    op.drop_table('compat_rule')
    op.drop_table('audit_event')
    op.drop_table('app_user')
    if op.get_bind().dialect.name == "postgresql":
        for name in ENUMS:
            postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
