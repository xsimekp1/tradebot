"""add_backtest_results

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-07
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backtest_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("strategy", sa.String(50), nullable=False),  # "multi_signal" | "walk_forward" | "rsi_single"
        sa.Column("train_days", sa.Integer, nullable=False),
        sa.Column("test_days", sa.Integer),           # NULL for non-walk-forward
        sa.Column("weights", postgresql.JSONB),        # signal weights used
        sa.Column("params", postgresql.JSONB),         # thresholds, trials, etc.
        sa.Column("in_sample", postgresql.JSONB),      # {return_pct, sharpe, win_rate, trades, max_dd}
        sa.Column("out_of_sample", postgresql.JSONB),  # NULL for non-walk-forward
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_backtest_results_symbol", "backtest_results", ["symbol"])
    op.create_index("ix_backtest_results_created_at", "backtest_results", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_backtest_results_created_at", table_name="backtest_results")
    op.drop_index("ix_backtest_results_symbol", table_name="backtest_results")
    op.drop_table("backtest_results")
