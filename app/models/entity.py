"""Named entities reused across articles."""

from __future__ import annotations

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Entity(Base):
    __tablename__ = "entities"
    __table_args__ = (UniqueConstraint("normalized_text", "type", name="uq_entities_norm_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_text: Mapped[str] = mapped_column(String(512), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
