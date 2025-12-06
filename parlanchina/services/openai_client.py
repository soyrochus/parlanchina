"""Shared async OpenAI client helpers.

This module centralizes creation of the async OpenAI client so both Ask and Agent
modes reuse the same configuration.
"""
from __future__ import annotations

import os
from typing import Optional, Tuple

from openai import AsyncAzureOpenAI, AsyncOpenAI

_client: Optional[AsyncOpenAI | AsyncAzureOpenAI] = None
_client_signature: Optional[Tuple[str, str | None, str | None, str | None]] = None


def _current_client_signature() -> tuple[str, str | None, str | None, str | None]:
    provider = (os.getenv("OPENAI_PROVIDER") or "openai").lower()
    api_key = os.getenv("OPENAI_API_KEY")
    api_base = os.getenv("OPENAI_API_BASE")
    api_version = os.getenv("OPENAI_API_VERSION")
    return provider, api_key, api_base, api_version


def get_async_client():
    """Return a cached async OpenAI client based on environment configuration."""

    global _client, _client_signature
    signature = _current_client_signature()
    if _client and _client_signature == signature:
        return _client

    provider, api_key, api_base, api_version = signature
    if provider == "azure":
        _client = AsyncAzureOpenAI(
            api_key=api_key,
            api_version=api_version,
            azure_endpoint=api_base,
        )
    else:
        _client = AsyncOpenAI(api_key=api_key, base_url=api_base)
    _client_signature = signature
    return _client


def reset_client_cache():
    """Clear cached client for testing or reconfiguration."""

    global _client, _client_signature
    _client = None
    _client_signature = None
