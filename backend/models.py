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
    STAGE = "stage"
    RESULT = "result"
    TOKEN = "token"
    DONE = "done"
    ERROR = "error"
