import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # "long" | "short"
    quantity: Mapped[float | None] = mapped_column(Numeric(18, 8))
    entry_price: Mapped[float | None] = mapped_column(Numeric(18, 8))
    exit_price: Mapped[float | None] = mapped_column(Numeric(18, 8))
    pnl: Mapped[float | None] = mapped_column(Numeric(18, 8))
    score: Mapped[float | None] = mapped_column(Numeric(10, 6))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alpaca_order_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
