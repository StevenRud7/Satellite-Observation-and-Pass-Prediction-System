"""add observers.is_saved

Separates locations the person explicitly saved from working observer rows
that pass prediction creates just to attach passes to. Every existing row
becomes is_saved = false, which empties the "Saved locations" list (it had
filled up with duplicates created by opening pass details); the rows
themselves, and the passes attached to them, are left untouched.

Revision ID: c7e41b9a52d0
Revises: ae89107ca46d
Create Date: 2026-10-15 12:00:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7e41b9a52d0"
down_revision: Optional[str] = "ae89107ca46d"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.add_column(
        "observers",
        sa.Column("is_saved", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("observers", "is_saved")