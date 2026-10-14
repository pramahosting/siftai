"""User management: active flag, administrator-assigned role, last sign-in.

Revision ID: 0003_user_management
"""
import sqlalchemy as sa
from alembic import op

revision="0003_user_management"
down_revision="0002_local_accounts"
branch_labels=None
depends_on=None

def _cols(): return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("users")}

def upgrade():
    have=_cols()
    with op.batch_alter_table("users") as b:
        if "is_active" not in have: b.add_column(sa.Column("is_active",sa.Boolean(),nullable=False,server_default=sa.true()))
        if "role_override" not in have: b.add_column(sa.Column("role_override",sa.String(40),nullable=True))
        if "last_login_at" not in have: b.add_column(sa.Column("last_login_at",sa.DateTime(timezone=True),nullable=True))

def downgrade():
    with op.batch_alter_table("users") as b:
        b.drop_column("last_login_at"); b.drop_column("role_override"); b.drop_column("is_active")
