"""vendor-created theater managers (admin approved, scoped to theaters)

Revision ID: 0006
Revises: 0005
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vendor_staff",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("vendor_id", sa.Integer(), sa.ForeignKey("vendor_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(12), server_default="pending", nullable=False),
        sa.Column("rejection_reason", sa.String(500)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_vendor_staff_vendor_status", "vendor_staff", ["vendor_id", "status"])
    op.create_table(
        "vendor_staff_theaters",
        sa.Column("staff_id", sa.Integer(), sa.ForeignKey("vendor_staff.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("venue_id", sa.Integer(), sa.ForeignKey("venues.id", ondelete="CASCADE"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("vendor_staff_theaters")
    op.drop_index("ix_vendor_staff_vendor_status", "vendor_staff")
    op.drop_table("vendor_staff")
