"""add is_demo to policies

Revision ID: 0002_add_is_demo_to_policies
Revises: 0001_initial
Create Date: 2026-09-24
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0002_add_is_demo_to_policies"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    try:
        op.add_column("policies", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default="0"))
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.drop_column("policies", "is_demo")
    except Exception:
        pass
