"""Article list and detail."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import ArticleFilters
from app.core.database import get_db
from app.schemas.article import ArticleDetail, ArticlePage
from app.services import articles as article_service

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("", response_model=ArticlePage)
def list_articles(filters: ArticleFilters, db: Session = Depends(get_db)):
    return article_service.list_articles(db, filters)


@router.get("/{article_id}", response_model=ArticleDetail)
def get_article(article_id: int, db: Session = Depends(get_db)):
    article = article_service.get_article(db, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article
