"""schema imports run as background jobs: EXTRACTING / FAILED states and an error code

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-11 19:30:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW = "status IN ('EXTRACTING', 'PROPOSED', 'APPROVED', 'REJECTED', 'FAILED')"
_OLD = "status IN ('PROPOSED', 'APPROVED', 'REJECTED')"


def upgrade() -> None:
    with op.batch_alter_table('schema_imports', schema=None) as batch_op:
        batch_op.drop_constraint('status', type_='check')
        batch_op.create_check_constraint('status', _NEW)
        batch_op.add_column(sa.Column('error_code', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.execute("DELETE FROM schema_imports WHERE status IN ('EXTRACTING', 'FAILED')")
    with op.batch_alter_table('schema_imports', schema=None) as batch_op:
        batch_op.drop_column('error_code')
        batch_op.drop_constraint('status', type_='check')
        batch_op.create_check_constraint('status', _OLD)
