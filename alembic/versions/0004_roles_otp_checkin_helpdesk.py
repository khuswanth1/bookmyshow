"""email verification + OTP, check-in staff & scans, helpdesk threads

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified", sa.Boolean(), server_default="false", nullable=False))
    op.execute("UPDATE users SET email_verified = true WHERE google_sub IS NOT NULL OR role <> 'user'")

    op.add_column("bookings", sa.Column("checked_in_at", sa.DateTime(timezone=True)))
    op.add_column("bookings", sa.Column("checked_in_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")))

    op.add_column("support_tickets", sa.Column("priority", sa.String(10), server_default="normal", nullable=False))
    op.add_column("support_tickets", sa.Column("category", sa.String(20), server_default="other", nullable=False))
    op.add_column("support_tickets", sa.Column("assigned_to_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")))
    op.add_column("support_tickets", sa.Column("resolved_at", sa.DateTime(timezone=True)))
    op.create_index("ix_support_tickets_assigned_to_id", "support_tickets", ["assigned_to_id"])
    op.create_index("ix_support_status_priority", "support_tickets", ["status", "priority"])

    op.create_table(
        "support_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("author_role", sa.String(20), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_internal", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_support_messages_ticket_id", "support_messages", ["ticket_id"])

    op.create_table(
        "otp_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_otp_lookup", "otp_codes", ["email", "purpose", "created_at"])

    op.create_table(
        "event_staff",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("event_id", "user_id"),
    )
    op.create_index("ix_event_staff_event_id", "event_staff", ["event_id"])
    op.create_index("ix_event_staff_user_id", "event_staff", ["user_id"])

    op.create_table(
        "checkins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="CASCADE")),
        sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id", ondelete="SET NULL")),
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("method", sa.String(10), server_default="scan", nullable=False),
        sa.Column("tickets", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_checkins_event_created", "checkins", ["event_id", "created_at"])


def downgrade() -> None:
    op.drop_table("checkins")
    op.drop_table("event_staff")
    op.drop_table("otp_codes")
    op.drop_table("support_messages")
    op.drop_index("ix_support_status_priority", "support_tickets")
    op.drop_index("ix_support_tickets_assigned_to_id", "support_tickets")
    for c in ("resolved_at", "assigned_to_id", "category", "priority"):
        op.drop_column("support_tickets", c)
    op.drop_column("bookings", "checked_in_by_id")
    op.drop_column("bookings", "checked_in_at")
    op.drop_column("users", "email_verified")
