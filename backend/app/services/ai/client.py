"""Thin wrapper around the Anthropic SDK. Every caller in this package must
tolerate `get_client()` returning None (no API key configured) and fall
back to a deterministic, rule-based behavior -- the product has to work
for a free trial before a customer ever adds billing/API credentials."""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings


@lru_cache
def get_client():
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    from anthropic import Anthropic

    return Anthropic(api_key=settings.anthropic_api_key)
