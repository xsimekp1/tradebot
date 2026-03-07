import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base


class EquityCurve(Base):
    __tablename__ = "equity_curve"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    total_equity: Mapped[float | None] = mapped_column(Numeric(18, 8))
    cash: Mapped[float | None] = mapped_column(Numeric(18, 8))
    portfolio_value: Mapped[float | None] = mapped_column(Numeric(18, 8))
    daily_pnl: Mapped[float | None] = mapped_column(Numeric(18, 8))
    cumulative_pnl: Mapped[float | None] = mapped_column(Numeric(18, 8))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
