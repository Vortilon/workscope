"""add_is_superseded_to_mpd_datasets

Revision ID: a1b2c3d4e5f6
Revises: 9a2b3c4d5e6f
Create Date: 2026-03-23

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "9a2b3c4d5e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "mpd_datasets",
        sa.Column("is_superseded", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("mpd_datasets", "is_superseded")
