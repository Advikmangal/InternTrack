"""Google identities, one-time OAuth states, and email review queue.

Revision ID: b20261026google
Revises: a1858528a6ae
"""
from alembic import op
import sqlalchemy as sa

revision = 'b20261026google'
down_revision = 'a1858528a6ae'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('google_accounts',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('subject', sa.String(255), nullable=False, unique=True),
        sa.Column('email', sa.String(254), nullable=False),
        sa.Column('refresh_token', sa.Text()),
        sa.Column('last_synced_at', sa.DateTime(timezone=True)),
        sa.Column('sync_started_at', sa.DateTime(timezone=True)),
        sa.Column('page_token', sa.Text()))
    op.create_table('google_oauth_states',
        sa.Column('state_hash', sa.String(64), primary_key=True),
        sa.Column('browser_hash', sa.String(64), nullable=False),
        sa.Column('verifier', sa.String(128), nullable=False),
        sa.Column('purpose', sa.String(20), nullable=False),
        sa.Column('session_hash', sa.String(64)),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('email_candidates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('message_id', sa.String(255), nullable=False),
        sa.Column('subject', sa.String(500), nullable=False),
        sa.Column('sender', sa.String(500), nullable=False),
        sa.Column('snippet', sa.Text(), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('suggested_status', sa.String(20), nullable=False),
        sa.Column('company', sa.String(160), nullable=False),
        sa.Column('role', sa.String(160), nullable=False),
        sa.Column('reviewed', sa.Boolean(), nullable=False),
        sa.Column('application_id', sa.Integer(), sa.ForeignKey('applications.id', ondelete='SET NULL')),
        sa.UniqueConstraint('user_id', 'message_id', name='uq_email_user_message'))
    op.create_index('ix_email_candidates_user_id', 'email_candidates', ['user_id'])


def downgrade():
    op.drop_table('email_candidates')
    op.drop_table('google_oauth_states')
    op.drop_table('google_accounts')
