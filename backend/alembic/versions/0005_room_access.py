"""Room access choices: open link, passcode, signed-in only, waiting room.

Revision ID: 0005_room_access
"""
import sqlalchemy as sa
from alembic import op

revision="0005_room_access"
down_revision="0004_rooms"
branch_labels=None
depends_on=None

def upgrade():
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("rooms")}     # new installs may already have them
    if "access" not in have: op.add_column("rooms", sa.Column("access", sa.String(16), nullable=False, server_default="open"))
    if "passcode" not in have: op.add_column("rooms", sa.Column("passcode", sa.String(40), nullable=True))
    if "waiting_room" not in have: op.add_column("rooms", sa.Column("waiting_room", sa.Boolean(), nullable=False, server_default=sa.false()))

def downgrade():
    for c in ("waiting_room", "passcode", "access"): op.drop_column("rooms", c)
