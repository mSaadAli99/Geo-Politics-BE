"""Initial schema for GeoPolitics AI.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("feed_url", sa.Text()),
        sa.Column("country_iso2", sa.String(length=2)),
        sa.Column("reliability_tier", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("reliability_score", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("domain", name="uq_sources_domain"),
    )
    op.create_table(
        "countries",
        sa.Column("iso2", sa.String(length=2), primary_key=True),
        sa.Column("iso3", sa.String(length=3), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("lat", sa.Float()),
        sa.Column("lng", sa.Float()),
        sa.Column("region", sa.String(length=32)),
    )
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text()),
        sa.Column("category", sa.String(length=64)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("article_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("primary_country_iso2", sa.String(length=2), sa.ForeignKey("countries.iso2")),
    )
    op.create_table(
        "articles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("url_hash", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("author", sa.String(length=512)),
        sa.Column("description", sa.Text()),
        sa.Column("content_text", sa.Text()),
        sa.Column("image_url", sa.Text()),
        sa.Column("language", sa.String(length=16)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("summary", sa.Text()),
        sa.Column("category", sa.String(length=64)),
        sa.Column("category_confidence", sa.Float()),
        sa.Column("sentiment_label", sa.String(length=16)),
        sa.Column("sentiment_score", sa.Float()),
        sa.Column("credibility_score", sa.Float()),
        sa.Column("credibility_level", sa.String(length=16)),
        sa.Column("credibility_factors", postgresql.JSONB()),
        sa.Column("keywords", postgresql.JSONB()),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id", ondelete="SET NULL")),
        sa.Column("is_duplicate_of", sa.Integer(), sa.ForeignKey("articles.id")),
        sa.Column("processing_status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("processing_error", sa.Text()),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('english', coalesce(title, '') || ' ' || "
                "coalesce(summary, '') || ' ' || coalesce(description, ''))",
                persisted=True,
            ),
        ),
        sa.UniqueConstraint("url", name="uq_articles_url"),
        sa.UniqueConstraint("url_hash", name="uq_articles_url_hash"),
    )
    op.create_index(
        "ix_articles_published_at",
        "articles",
        ["published_at"],
        postgresql_ops={"published_at": "DESC"},
    )
    op.create_index("ix_articles_category", "articles", ["category"])
    op.create_index("ix_articles_sentiment_label", "articles", ["sentiment_label"])
    op.create_index("ix_articles_source_id", "articles", ["source_id"])
    op.create_index("ix_articles_event_id", "articles", ["event_id"])
    op.create_index("ix_articles_processing_status", "articles", ["processing_status"])
    op.create_index(
        "ix_articles_search_vector",
        "articles",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.create_table(
        "article_countries",
        sa.Column("article_id", sa.Integer(), sa.ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("country_iso2", sa.String(length=2), sa.ForeignKey("countries.iso2"), primary_key=True),
        sa.Column("mentions", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_article_countries_iso2", "article_countries", ["country_iso2"])
    op.create_table(
        "entities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("text", sa.String(length=512), nullable=False),
        sa.Column("normalized_text", sa.String(length=512), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.UniqueConstraint("normalized_text", "type", name="uq_entities_norm_type"),
    )
    op.create_table(
        "article_entities",
        sa.Column("article_id", sa.Integer(), sa.ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("entity_id", sa.Integer(), sa.ForeignKey("entities.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("mentions", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_table(
        "topics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("keywords", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("article_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trend_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("growth_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "article_topics",
        sa.Column("article_id", sa.Integer(), sa.ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_index("ix_article_topics_topic", "article_topics", ["topic_id"])
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id")),
        sa.Column("fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicates", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
    )
    op.create_index("ix_ingestion_runs_started", "ingestion_runs", ["started_at"])
    op.create_table(
        "model_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("task", sa.String(length=64), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column("dataset", sa.String(length=255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("model_evaluations")
    op.drop_table("ingestion_runs")
    op.drop_table("article_topics")
    op.drop_table("topics")
    op.drop_table("article_entities")
    op.drop_table("entities")
    op.drop_table("article_countries")
    op.drop_table("articles")
    op.drop_table("events")
    op.drop_table("countries")
    op.drop_table("sources")
