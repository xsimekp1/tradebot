"""initial_trading_tables

Revision ID: 0001
Revises:
Create Date: 2026-03-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trades",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 8)),
        sa.Column("entry_price", sa.Numeric(18, 8)),
        sa.Column("exit_price", sa.Numeric(18, 8)),
        sa.Column("pnl", sa.Numeric(18, 8)),
        sa.Column("score", sa.Numeric(10, 6)),
        sa.Column("opened_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("alpaca_order_id", sa.String(100)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "trading_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("signal_name", sa.String(50), nullable=False),
        sa.Column("value", sa.Numeric(10, 6)),
        sa.Column("weight", sa.Numeric(10, 6)),
        sa.Column("score_contribution", sa.Numeric(10, 6)),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "equity_curve",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("total_equity", sa.Numeric(18, 8)),
        sa.Column("cash", sa.Numeric(18, 8)),
        sa.Column("portfolio_value", sa.Numeric(18, 8)),
        sa.Column("daily_pnl", sa.Numeric(18, 8)),
        sa.Column("cumulative_pnl", sa.Numeric(18, 8)),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "signal_weights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("weights", postgresql.JSONB, nullable=False),
        sa.Column("performance", postgresql.JSONB),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Indexes for common queries
    op.create_index("ix_trades_symbol_opened_at", "trades", ["symbol", "opened_at"])
    op.create_index("ix_trading_signals_timestamp", "trading_signals", ["timestamp"])
    op.create_index("ix_trading_signals_symbol", "trading_signals", ["symbol"])
    op.create_index("ix_equity_curve_timestamp", "equity_curve", ["timestamp"])
    op.create_index("ix_signal_weights_is_active", "signal_weights", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_signal_weights_is_active", table_name="signal_weights")
    op.drop_index("ix_equity_curve_timestamp", table_name="equity_curve")
    op.drop_index("ix_trading_signals_symbol", table_name="trading_signals")
    op.drop_index("ix_trading_signals_timestamp", table_name="trading_signals")
    op.drop_index("ix_trades_symbol_opened_at", table_name="trades")
    op.drop_table("signal_weights")
    op.drop_table("equity_curve")
    op.drop_table("trading_signals")
    op.drop_table("trades")
