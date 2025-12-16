"""Add email sync tables and columns

Revision ID: f8c9d4e5f6a7
Revises: 2907bb853969
Create Date: 2025-12-13

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f8c9d4e5f6a7'
down_revision = '2907bb853969'
branch_labels = None
depends_on = None


def upgrade():
    # Create email_sync_config table
    op.create_table(
        'email_sync_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('email_provider', sa.String(50), server_default='gmail', nullable=False),
        sa.Column('email_address', sa.String(255), nullable=False),
        sa.Column('oauth_token_encrypted', sa.Text(), nullable=True),
        sa.Column('last_sync_date', sa.DateTime(), nullable=True),
        sa.Column('sync_enabled', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('sync_frequency_hours', sa.Integer(), server_default='24', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create email_processing_log table
    op.create_table(
        'email_processing_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('email_message_id', sa.String(255), nullable=False),
        sa.Column('email_subject', sa.Text(), nullable=True),
        sa.Column('email_date', sa.String(255), nullable=True),
        sa.Column('processed_at', sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column('processing_status', sa.String(50), nullable=True),
        sa.Column('amazon_order_id', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['amazon_order_id'], ['amazon_orders.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email_message_id')
    )
    
    # Add new columns to amazon_orders
    with op.batch_alter_table('amazon_orders') as batch_op:
        batch_op.add_column(sa.Column('source_type', sa.String(50), server_default='csv', nullable=True))
        batch_op.add_column(sa.Column('email_message_id', sa.String(255), nullable=True))
        batch_op.add_column(sa.Column('raw_email_html', sa.Text(), nullable=True))


def downgrade():
    # Remove columns from amazon_orders
    with op.batch_alter_table('amazon_orders') as batch_op:
        batch_op.drop_column('raw_email_html')
        batch_op.drop_column('email_message_id')
        batch_op.drop_column('source_type')
    
    # Drop tables
    op.drop_table('email_processing_log')
    op.drop_table('email_sync_config')
