"""Article list and detail queries."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Article, ArticleCountry, ArticleEntity, ArticleTopic
from app.services.filters import ArticleQuery
from app.services.query import count_stmt, page_count
from app.services.serialize import article_card, article_detail


_ARTICLE_LOAD = (
    selectinload(Article.source),
    selectinload(Article.country_links).selectinload(ArticleCountry.country),
)


def _filtered(filters: ArticleQuery):
    conds = [Article.is_duplicate_of.is_(None)]
    if filters.category:
        conds.append(Article.category == filters.category)
    if filters.sentiment:
        conds.append(Article.sentiment_label == filters.sentiment)
    if filters.source_id:
        conds.append(Article.source_id == filters.source_id)
    if filters.event_id:
        conds.append(Article.event_id == filters.event_id)
    if filters.from_dt:
        conds.append(Article.published_at >= filters.from_dt)
    if filters.to_dt:
        conds.append(Article.published_at <= filters.to_dt)
    if filters.min_credibility is not None:
        conds.append(Article.credibility_score >= filters.min_credibility)
    stmt = select(Article).where(*conds)
    if filters.country:
        stmt = stmt.where(
            Article.id.in_(
                select(ArticleCountry.article_id).where(
                    ArticleCountry.country_iso2 == filters.country
                )
            )
        )
    if filters.topic_id:
        stmt = stmt.where(
            Article.id.in_(
                select(ArticleTopic.article_id).where(ArticleTopic.topic_id == filters.topic_id)
            )
        )
    rank = None
    if filters.q:
        tsq = func.plainto_tsquery("english", filters.q)
        stmt = stmt.where(Article.search_vector.op("@@")(tsq))
        rank = func.ts_rank(Article.search_vector, tsq)
    if filters.sort == "credibility":
        stmt = stmt.order_by(
            Article.credibility_score.desc().nulls_last(),
            Article.published_at.desc().nulls_last(),
            Article.id.desc(),
        )
    elif filters.sort == "relevance" and rank is not None:
        stmt = stmt.order_by(rank.desc(), Article.published_at.desc().nulls_last(), Article.id.desc())
    else:
        stmt = stmt.order_by(Article.published_at.desc().nulls_last(), Article.id.desc())
    return stmt


def list_articles(db: Session, filters: ArticleQuery) -> dict:
    """Paginated article cards. Duplicates are excluded."""
    stmt = _filtered(filters)
    total = count_stmt(db, stmt)
    rows = db.scalars(
        stmt.options(*_ARTICLE_LOAD)
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
    ).unique().all()
    return {
        "items": [article_card(row) for row in rows],
        "total": total,
        "page": filters.page,
        "page_size": filters.page_size,
        "pages": page_count(total, filters.page_size),
    }


def get_article(db: Session, article_id: int):
    """Article detail, or None when the id does not exist."""
    article = db.scalar(
        select(Article)
        .where(Article.id == article_id)
        .options(
            *_ARTICLE_LOAD,
            selectinload(Article.entity_links).selectinload(ArticleEntity.entity),
            selectinload(Article.topic_links).selectinload(ArticleTopic.topic),
        )
    )
    if article is None:
        return None
    related: list[Article] = []
    if article.event_id:
        related = db.scalars(
            select(Article)
            .where(
                Article.event_id == article.event_id,
                Article.id != article.id,
                Article.is_duplicate_of.is_(None),
            )
            .options(*_ARTICLE_LOAD)
            .order_by(Article.published_at.desc().nulls_last())
            .limit(5)
        ).unique().all()
    return article_detail(article, list(related))
