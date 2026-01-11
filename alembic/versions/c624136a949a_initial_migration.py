"""Initial migration

Revision ID: c624136a949a
Revises: 
Create Date: 2025-01-17 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'c624136a949a'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create sequence for payment_events.seq
    op.execute("CREATE SEQUENCE payment_events_seq START 1")
    
    # Create clients table
    op.create_table(
        'clients',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('machine_id', sa.String(255), nullable=False, unique=True),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('allowed_ips', postgresql.ARRAY(postgresql.CIDR), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('client_metadata', postgresql.JSON, nullable=True),
    )
    op.create_index('ix_clients_machine_id', 'clients', ['machine_id'])
    
    # Create client_auth_events table
    op.create_table(
        'client_auth_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('client_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('ip', postgresql.INET, nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('details', postgresql.JSON, nullable=True),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
    )
    op.create_index('ix_client_auth_events_client_id', 'client_auth_events', ['client_id'])
    op.create_index('ix_client_auth_events_created_at', 'client_auth_events', ['created_at'])
    
    # Create payment_requests table
    op.create_table(
        'payment_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('client_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('external_code', sa.String(64), nullable=False),
        sa.Column('payment_method', sa.String(50), nullable=False),
        sa.Column('amount', sa.Numeric(18, 8), nullable=False),
        sa.Column('currency', sa.String(10), nullable=False),
        sa.Column('amount_sats', sa.BigInteger(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('callback_url', sa.Text(), nullable=True),
        sa.Column('redirect_url', sa.Text(), nullable=True),
        sa.Column('payment_metadata', postgresql.JSON, nullable=False, server_default='{}'),
        sa.Column('idempotency_key', sa.String(255), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='CREATED'),
        sa.Column('status_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('monitor_until', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finalized_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ),
        sa.UniqueConstraint('client_id', 'idempotency_key', name='uq_client_idempotency'),
    )
    op.create_index('ix_payment_requests_client_id', 'payment_requests', ['client_id'])
    op.create_index('ix_payment_requests_status', 'payment_requests', ['status'])
    op.create_index('ix_payment_requests_created_at', 'payment_requests', ['created_at'])
    op.create_index('idx_payment_client_created', 'payment_requests', ['client_id', 'created_at'])
    op.create_index('idx_payment_status_monitor', 'payment_requests', ['status', 'monitor_until'])
    
    # Create provider_invoices table
    op.create_table(
        'provider_invoices',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('payment_request_id', postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('provider_invoice_id', sa.String(255), nullable=False),
        sa.Column('store_id', sa.String(255), nullable=False),
        sa.Column('checkout_link', sa.Text(), nullable=True),
        sa.Column('bolt11', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('raw_create_response', postgresql.JSON, nullable=False),
        sa.Column('raw_last_status', postgresql.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['payment_request_id'], ['payment_requests.id'], ),
    )
    op.create_index('ix_provider_invoices_payment_request_id', 'provider_invoices', ['payment_request_id'])
    op.create_index('ix_provider_invoices_provider_invoice_id', 'provider_invoices', ['provider_invoice_id'])
    
    # Create payment_events table
    op.create_table(
        'payment_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('seq', sa.BigInteger(), nullable=False, server_default=sa.text("nextval('payment_events_seq')")),
        sa.Column('payment_request_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('old_status', sa.String(50), nullable=True),
        sa.Column('new_status', sa.String(50), nullable=True),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('payload', postgresql.JSON, nullable=True),
        sa.ForeignKeyConstraint(['payment_request_id'], ['payment_requests.id'], ),
    )
    op.create_index('ix_payment_events_seq', 'payment_events', ['seq'], unique=True)
    op.create_index('ix_payment_events_payment_request_id', 'payment_events', ['payment_request_id'])
    op.create_index('ix_payment_events_created_at', 'payment_events', ['created_at'])
    op.create_index('idx_payment_events_payment_seq', 'payment_events', ['payment_request_id', 'seq'])


def downgrade() -> None:
    op.drop_index('idx_payment_events_payment_seq', table_name='payment_events')
    op.drop_index('ix_payment_events_created_at', table_name='payment_events')
    op.drop_index('ix_payment_events_payment_request_id', table_name='payment_events')
    op.drop_index('ix_payment_events_seq', table_name='payment_events')
    op.drop_table('payment_events')
    op.drop_index('ix_provider_invoices_provider_invoice_id', table_name='provider_invoices')
    op.drop_index('ix_provider_invoices_payment_request_id', table_name='provider_invoices')
    op.drop_table('provider_invoices')
    op.drop_index('idx_payment_status_monitor', table_name='payment_requests')
    op.drop_index('idx_payment_client_created', table_name='payment_requests')
    op.drop_index('ix_payment_requests_created_at', table_name='payment_requests')
    op.drop_index('ix_payment_requests_status', table_name='payment_requests')
    op.drop_index('ix_payment_requests_client_id', table_name='payment_requests')
    op.drop_table('payment_requests')
    op.drop_index('ix_client_auth_events_created_at', table_name='client_auth_events')
    op.drop_index('ix_client_auth_events_client_id', table_name='client_auth_events')
    op.drop_table('client_auth_events')
    op.drop_index('ix_clients_machine_id', table_name='clients')
    op.drop_table('clients')
    op.execute("DROP SEQUENCE payment_events_seq")
