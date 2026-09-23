"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-23

The initial schema is created from the SQLAlchemy metadata so that the models
remain the single source of truth. Subsequent migrations should be generated
with `alembic revision --autogenerate -m "..."`.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.core.database import Base
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    from app.core.database import Base
    import app.models  # noqa: F401

    Base.metadata.drop_all(bind=op.get_bind())
