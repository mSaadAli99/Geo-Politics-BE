"""Shared API types."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer


def _to_utc_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


UTCDateTime = Annotated[
    datetime,
    PlainSerializer(_to_utc_z, return_type=str, when_used="json"),
]


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SourceBrief(APIModel):
    id: int
    name: str
    domain: str
    reliability_tier: str


class CountryBrief(APIModel):
    iso2: str
    name: str


class SentimentOut(APIModel):
    label: str
    score: float


class CredibilityBrief(APIModel):
    score: int
    level: str


class CredibilityFactor(APIModel):
    name: str
    value: float
    weight: float
    explanation: str


class CredibilityDetail(CredibilityBrief):
    factors: list[CredibilityFactor]
    disclaimer: str


DISCLAIMER = "Indicator based on defined factors, not a fact-check."
