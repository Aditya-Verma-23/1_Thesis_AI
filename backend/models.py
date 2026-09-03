"""Pydantic v2 schemas for Thesis AI."""
from __future__ import annotations

from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=2000)
    session_id: str | None = None
    sources: list[str] | None = None
    filters: dict | None = None
    is_followup: bool = False
    thesis_context: str | None = None  # the current thesis text for follow-up chats
    original_query: str | None = None  # the original thesis topic for follow-up context
    chat_history: list[dict] | None = None  # previous chat messages for follow-up context


class SearchResult(BaseModel):
    index: int
    title: str
    url: str | None = None
    snippet: str = ""
    source: str = "web"  # "duckduckgo" | "google" | "arxiv"
    image_url: str | None = None
    full_text: str = ""


class SynthesisResult(BaseModel):
    session_id: str
    query: str
    results: list[SearchResult]
    paper_text: str


class StreamEventType(str, Enum):
    STAGE    = "stage"
    SCRAPING = "scraping"   # per-URL scrape progress
    RESULT   = "result"
    TOKEN    = "token"
    DONE     = "done"
    ERROR    = "error"
