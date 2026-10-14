"""google calendar connections + per-booking sync state

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "calendar_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("refresh_token_enc", sa.Text(), nullable=False),
        sa.Column("status", sa.String(12), server_default="connected", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("bookings", sa.Column("calendar_status", sa.String(10)))
    op.add_column("bookings", sa.Column("calendar_event_id", sa.String(64)))
    op.add_column("bookings", sa.Column("calendar_synced_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("bookings", "calendar_synced_at")
    op.drop_column("bookings", "calendar_event_id")
    op.drop_column("bookings", "calendar_status")
    op.drop_table("calendar_connections")
