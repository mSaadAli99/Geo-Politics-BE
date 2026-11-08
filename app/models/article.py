"""Articles and the link tables that hang off them."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

_SEARCH_SQL = (
    "to_tsvector('english', coalesce(title, '') || ' ' || "
    "coalesce(summary, '') || ' ' || coalesce(description, ''))"
)


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        Index(
            "ix_articles_published_at",
            "published_at",
            postgresql_ops={"published_at": "DESC"},
        ),
        Index("ix_articles_category", "category"),
        Index("ix_articles_sentiment_label", "sentiment_label"),
        Index("ix_articles_source_id", "source_id"),
        Index("ix_articles_event_id", "event_id"),
        Index("ix_articles_processing_status", "processing_status"),
        Index("ix_articles_search_vector", "search_vector", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), nullable=False)
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    content_text: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(16))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    summary: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(64))
    category_confidence: Mapped[float | None] = mapped_column(Float)
    sentiment_label: Mapped[str | None] = mapped_column(String(16))
    sentiment_score: Mapped[float | None] = mapped_column(Float)
    credibility_score: Mapped[float | None] = mapped_column(Float)
    credibility_level: Mapped[str | None] = mapped_column(String(16))
    credibility_factors: Mapped[list | None] = mapped_column(JSONB)
    keywords: Mapped[list | None] = mapped_column(JSONB)

    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"))
    is_duplicate_of: Mapped[int | None] = mapped_column(ForeignKey("articles.id"))

    processing_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    processing_error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed(_SEARCH_SQL, persisted=True)
    )

    source: Mapped["Source"] = relationship(back_populates="articles")  # noqa: F821
    event: Mapped["Event | None"] = relationship(back_populates="articles")  # noqa: F821
    country_links: Mapped[list["ArticleCountry"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )
    entity_links: Mapped[list["ArticleEntity"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )
    topic_links: Mapped[list["ArticleTopic"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )


class ArticleCountry(Base):
    __tablename__ = "article_countries"

    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
    country_iso2: Mapped[str] = mapped_column(ForeignKey("countries.iso2"), primary_key=True)
    mentions: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_primary: Mapped[bool] = mapped_column(nullable=False, default=False)

    article: Mapped[Article] = relationship(back_populates="country_links")
    country: Mapped["Country"] = relationship()  # noqa: F821


class ArticleEntity(Base):
    __tablename__ = "article_entities"

    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True
    )
    mentions: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    article: Mapped[Article] = relationship(back_populates="entity_links")
    entity: Mapped["Entity"] = relationship()  # noqa: F821


class ArticleTopic(Base):
    __tablename__ = "article_topics"

    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )

    article: Mapped[Article] = relationship(back_populates="topic_links")
    topic: Mapped["Topic"] = relationship()  # noqa: F821
