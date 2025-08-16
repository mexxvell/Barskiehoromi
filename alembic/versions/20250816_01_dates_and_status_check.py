"""Convert TEXT dates to proper types and add status check constraint

Revision ID: 20250816_01
Revises: 
Create Date: 2025-08-16
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250816_01'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Convert date columns stored as TEXT to DATE where applicable
    # user_log.date
    op.execute("""
        ALTER TABLE user_log
        ALTER COLUMN date TYPE DATE USING date::date
    """)
    # merch_orders.date -> DATE
    op.execute("""
        ALTER TABLE merch_orders
        ALTER COLUMN date TYPE DATE USING date::date
    """)
    # merch_pending.date -> DATE
    op.execute("""
        ALTER TABLE merch_pending
        ALTER COLUMN date TYPE DATE USING date::date
    """)
    # subscriptions.date_subscribed -> DATE
    op.execute("""
        ALTER TABLE subscriptions
        ALTER COLUMN date_subscribed TYPE DATE USING date_subscribed::date
    """)
    # unsubscriptions.date_unsubscribed -> DATE
    op.execute("""
        ALTER TABLE unsubscriptions
        ALTER COLUMN date_unsubscribed TYPE DATE USING date_unsubscribed::date
    """)
    # referrals.date_registered -> DATE
    op.execute("""
        ALTER TABLE referrals
        ALTER COLUMN date_registered TYPE DATE USING date_registered::date
    """)

    # Add CHECK constraint for merch_orders.status
    op.execute("""
        ALTER TABLE merch_orders
        ADD CONSTRAINT merch_orders_status_check CHECK (status IN ('В обработке','Отправлен','Доставлен','Отклонён'))
    """)


def downgrade():
    # Remove CHECK constraint
    op.execute("ALTER TABLE merch_orders DROP CONSTRAINT IF EXISTS merch_orders_status_check")
    # Convert dates back to TEXT (not recommended)
    op.execute("ALTER TABLE user_log ALTER COLUMN date TYPE TEXT")
    op.execute("ALTER TABLE merch_orders ALTER COLUMN date TYPE TEXT")
    op.execute("ALTER TABLE merch_pending ALTER COLUMN date TYPE TEXT")
    op.execute("ALTER TABLE subscriptions ALTER COLUMN date_subscribed TYPE TEXT")
    op.execute("ALTER TABLE unsubscriptions ALTER COLUMN date_unsubscribed TYPE TEXT")
    op.execute("ALTER TABLE referrals ALTER COLUMN date_registered TYPE TEXT")
