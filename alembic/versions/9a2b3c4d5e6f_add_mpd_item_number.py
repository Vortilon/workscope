"""add_mpd_item_number

Revision ID: 9a2b3c4d5e6f
Revises: 8f1a9c2d1b07
Create Date: 2026-03-23

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9a2b3c4d5e6f"
down_revision: Union[str, None] = "8f1a9c2d1b07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mpd_tasks",
        sa.Column("mpd_item_number", sa.String(256), nullable=True),
    )
    op.create_index("ix_mpd_tasks_mpd_item_number", "mpd_tasks", ["mpd_item_number"])


def downgrade() -> None:
    op.drop_index("ix_mpd_tasks_mpd_item_number", table_name="mpd_tasks")
    op.drop_column("mpd_tasks", "mpd_item_number")
