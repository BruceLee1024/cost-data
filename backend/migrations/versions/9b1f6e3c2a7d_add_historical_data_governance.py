"""add historical data governance

Revision ID: 9b1f6e3c2a7d
Revises: 57c3f31be6ee
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "9b1f6e3c2a7d"
down_revision: Union[str, Sequence[str], None] = "57c3f31be6ee"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "price_context" not in _columns("projects"):
        with op.batch_alter_table("projects") as batch:
            batch.add_column(sa.Column("price_context", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    if "hierarchy_path" not in _columns("cost_items"):
        with op.batch_alter_table("cost_items") as batch:
            batch.add_column(sa.Column("hierarchy_path", sa.Text()))
            batch.add_column(sa.Column("data_status", sa.String(24), nullable=False, server_default="parsed"))
            batch.create_index("ix_cost_items_data_status", ["data_status"], unique=False)
    if "link_status" not in _columns("rate_components"):
        with op.batch_alter_table("rate_components") as batch:
            batch.add_column(sa.Column("link_status", sa.String(24), nullable=False, server_default="pending"))
            batch.add_column(sa.Column("link_evidence", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
            batch.create_index("ix_rate_components_link_status", ["link_status"], unique=False)
    if "link_status" not in _columns("quota_items"):
        with op.batch_alter_table("quota_items") as batch:
            batch.add_column(sa.Column("link_status", sa.String(24), nullable=False, server_default="pending"))
            batch.add_column(sa.Column("link_evidence", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
            batch.create_index("ix_quota_items_link_status", ["link_status"], unique=False)
    if "source_category" not in _columns("resource_items"):
        with op.batch_alter_table("resource_items") as batch:
            batch.add_column(sa.Column("source_category", sa.String(120)))
            batch.add_column(sa.Column("data_status", sa.String(24), nullable=False, server_default="parsed"))
            batch.create_index("ix_resource_items_data_status", ["data_status"], unique=False)
    if "source_cells" not in _columns("resource_items"):
        with op.batch_alter_table("resource_items") as batch:
            batch.add_column(sa.Column("source_cells", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    with op.batch_alter_table("resource_items") as batch:
        batch.drop_index("ix_resource_items_data_status")
        batch.drop_column("data_status")
        batch.drop_column("source_cells")
        batch.drop_column("source_category")
    with op.batch_alter_table("quota_items") as batch:
        batch.drop_index("ix_quota_items_link_status")
        batch.drop_column("link_evidence")
        batch.drop_column("link_status")
    with op.batch_alter_table("rate_components") as batch:
        batch.drop_index("ix_rate_components_link_status")
        batch.drop_column("link_evidence")
        batch.drop_column("link_status")
    with op.batch_alter_table("cost_items") as batch:
        batch.drop_index("ix_cost_items_data_status")
        batch.drop_column("data_status")
        batch.drop_column("hierarchy_path")
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("price_context")
