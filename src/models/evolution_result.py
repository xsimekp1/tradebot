import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base


class EvolutionResult(Base):
    __tablename__ = "evolution_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    version_before: Mapped[int] = mapped_column(Integer, nullable=False)
    version_after: Mapped[int | None] = mapped_column(Integer)
    current_sharpe: Mapped[float | None] = mapped_column(Numeric(10, 6))
    best_sharpe: Mapped[float | None] = mapped_column(Numeric(10, 6))
    mutations_tried: Mapped[int] = mapped_column(Integer, nullable=False)
    model_changed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    improvement: Mapped[float | None] = mapped_column(Numeric(10, 6))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
