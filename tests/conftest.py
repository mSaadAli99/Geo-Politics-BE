"""Fixtures that need PostgreSQL. Unit tests do not use these."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.database import get_db
from app.main import app
from app.models import Base

ADMIN_URL = os.getenv(
    "TEST_ADMIN_URL",
    "postgresql+psycopg://geopolitics:geopolitics@localhost:5432/geopolitics",
)
TEST_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://geopolitics:geopolitics@localhost:5432/geopolitics_test",
)


@pytest.fixture(scope="session")
def db_engine():
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.execute(text("SELECT 1"))
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = 'geopolitics_test'")
            ).scalar()
            if not exists:
                connection.execute(text("CREATE DATABASE geopolitics_test"))
    except Exception as exc:
        admin.dispose()
        pytest.skip(f"PostgreSQL is not available: {exc}")
    admin.dispose()
    engine = create_engine(TEST_URL, pool_pre_ping=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine):
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        cleanup = factory()
        cleanup.execute(
            text(
                "TRUNCATE TABLE article_topics, article_entities, article_countries, "
                "articles, topics, entities, events, ingestion_runs, model_evaluations, "
                "sources, countries RESTART IDENTITY CASCADE"
            )
        )
        cleanup.commit()
        cleanup.close()


@pytest.fixture
def client(db):
    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
