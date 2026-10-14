"""Local sign-up accounts (local demo mode).

Revision ID: 0002_local_accounts
"""
from alembic import op
from app.models import LocalAccount

revision="0002_local_accounts"
down_revision="0001_initial"
branch_labels=None
depends_on=None

def upgrade(): LocalAccount.__table__.create(bind=op.get_bind(), checkfirst=True)
def downgrade(): LocalAccount.__table__.drop(bind=op.get_bind(), checkfirst=True)
