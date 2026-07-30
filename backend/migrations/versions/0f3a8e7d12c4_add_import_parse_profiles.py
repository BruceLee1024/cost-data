"""add import parse profiles

Revision ID: 0f3a8e7d12c4
Revises: bd9d97625f1a
Create Date: 2026-07-30 21:20:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0f3a8e7d12c4"
down_revision: Union[str, Sequence[str], None] = "bd9d97625f1a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("import_jobs") as batch_op:
        batch_op.add_column(sa.Column("parse_preview", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    with op.batch_alter_table("cost_items") as batch_op:
        batch_op.add_column(sa.Column("source_cells", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
        batch_op.add_column(sa.Column("import_attributes", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.create_table(
        "parser_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("report_type", sa.String(length=80), nullable=False),
        sa.Column("mapping", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint"),
    )
    op.create_index("ix_parser_profiles_fingerprint", "parser_profiles", ["fingerprint"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_parser_profiles_fingerprint", table_name="parser_profiles")
    op.drop_table("parser_profiles")
    with op.batch_alter_table("cost_items") as batch_op:
        batch_op.drop_column("import_attributes")
        batch_op.drop_column("source_cells")
    with op.batch_alter_table("import_jobs") as batch_op:
        batch_op.drop_column("parse_preview")
