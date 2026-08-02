"""add phase one data assets

Revision ID: 57c3f31be6ee
Revises: 0f3a8e7d12c4
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "57c3f31be6ee"
down_revision: Union[str, Sequence[str], None] = "0f3a8e7d12c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "profile" not in {column["name"] for column in inspector.get_columns("projects")}:
        with op.batch_alter_table("projects") as batch_op:
            batch_op.add_column(sa.Column("profile", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    if "unit_conversions" not in inspector.get_table_names():
        op.create_table("unit_conversions", sa.Column("id", sa.String(36), primary_key=True), sa.Column("source_unit", sa.String(40), nullable=False), sa.Column("target_unit", sa.String(40), nullable=False), sa.Column("factor_value", sa.BigInteger(), nullable=False), sa.Column("factor_scale", sa.Integer(), nullable=False), sa.Column("basis", sa.String(500), nullable=False), sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False), sa.UniqueConstraint("source_unit", "target_unit", name="ix_unit_conversion_source_target"))
    if "metric_templates" not in inspector.get_table_names():
        op.create_table("metric_templates", sa.Column("id", sa.String(36), primary_key=True), sa.Column("code", sa.String(80), nullable=False, unique=True), sa.Column("name", sa.String(160), nullable=False), sa.Column("unit", sa.String(40), nullable=False), sa.Column("formula", sa.Text(), nullable=False), sa.Column("description", sa.Text()), sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("updated_at", sa.DateTime(), nullable=False))


def downgrade() -> None:
    op.drop_table("metric_templates")
    op.drop_table("unit_conversions")
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("profile")
