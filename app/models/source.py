"""News sources (RSS feeds, APIs, and outlets discovered at ingest time)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    feed_url: Mapped[str | None] = mapped_column(Text)
    country_iso2: Mapped[str | None] = mapped_column(String(2))
    reliability_tier: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    reliability_score: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    articles: Mapped[list["Article"]] = relationship(back_populates="source")  # noqa: F821
