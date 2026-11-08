"""Import every model so Alembic and create_all see the full metadata."""

from app.models.article import Article, ArticleCountry, ArticleEntity, ArticleTopic
from app.models.base import Base
from app.models.country import Country
from app.models.entity import Entity
from app.models.event import Event
from app.models.ops import IngestionRun, ModelEvaluation
from app.models.source import Source
from app.models.topic import Topic

__all__ = [
    "Article",
    "ArticleCountry",
    "ArticleEntity",
    "ArticleTopic",
    "Base",
    "Country",
    "Entity",
    "Event",
    "IngestionRun",
    "ModelEvaluation",
    "Source",
    "Topic",
]
