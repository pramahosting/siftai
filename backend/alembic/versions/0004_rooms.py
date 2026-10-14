"""Built-in meeting rooms and their recordings.

Revision ID: 0004_rooms
"""
import sqlalchemy as sa
from alembic import op

revision="0004_rooms"
down_revision="0003_user_management"
branch_labels=None
depends_on=None

def upgrade():
    have=set(sa.inspect(op.get_bind()).get_table_names())
    if "rooms" not in have:
        op.create_table("rooms",
            sa.Column("id",sa.String(36),primary_key=True),
            sa.Column("code",sa.String(40),nullable=False),
            sa.Column("host_id",sa.String(36),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
            sa.Column("meeting_id",sa.String(36),sa.ForeignKey("meetings.id",ondelete="SET NULL"),nullable=True),
            sa.Column("title",sa.String(200),nullable=False),
            sa.Column("allow_guests",sa.Boolean(),nullable=False,server_default=sa.true()),
            sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
            sa.Column("ended_at",sa.DateTime(timezone=True),nullable=True))
        op.create_index("ix_rooms_code","rooms",["code"],unique=True)
        op.create_index("ix_rooms_host_id","rooms",["host_id"])
        op.create_index("ix_rooms_meeting_id","rooms",["meeting_id"])
    if "room_recordings" not in have:
        op.create_table("room_recordings",
            sa.Column("id",sa.String(36),primary_key=True),
            sa.Column("room_id",sa.String(36),sa.ForeignKey("rooms.id",ondelete="CASCADE"),nullable=False),
            sa.Column("path",sa.Text(),nullable=False),
            sa.Column("size_bytes",sa.Integer(),nullable=False,server_default="0"),
            sa.Column("has_video",sa.Boolean(),nullable=False,server_default=sa.true()),
            sa.Column("created_at",sa.DateTime(timezone=True),nullable=False))
        op.create_index("ix_room_recordings_room_id","room_recordings",["room_id"])

def downgrade():
    op.drop_table("room_recordings"); op.drop_table("rooms")
