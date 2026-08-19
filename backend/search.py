"""Web search engine integration: DuckDuckGo + Google, run concurrently.

Pattern taken directly from the user's Google.txt reference file.
Both engines run in threads (asyncio.to_thread) so the FastAPI event
loop is never blocked. Results are merged and deduplicated by URL.
"""
from __future__ import annotations

import asyncio
from loguru import logger

from models import SearchResult

MAX_PER_ENGINE = 7   # fetch more than 10 so dedup still yields 10
TOTAL_RESULTS  = 10
TIMEOUT_S      = 20


# ── Synchronous helpers (executed in thread-pool) ─────────────────────────────

def _ddg_sync(query: str, max_results: int) -> list[dict]:
    """DuckDuckGo text search using the ddgs package."""
    try:
        from ddgs import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title":   r.get("title", ""),
                    "url":     r.get("href", ""),
                    "snippet": r.get("body", ""),
                    "source":  "duckduckgo",
                })
        return results
    except Exception as exc:
        logger.warning(f"DuckDuckGo failed: {exc}")
        return []


def _google_sync(query: str, max_results: int) -> list[dict]:
    """Google search using googlesearch-python (keyless scrape)."""
    try:
        from googlesearch import search
        results = []
        for url in search(query, num_results=max_results, lang="en"):
            results.append({
                "title":   "",
                "url":     url,
                "snippet": "",
                "source":  "google",
            })
        return results
    except Exception as exc:
        logger.warning(f"Google search failed: {exc}")
        return []


# ── Public async function ──────────────────────────────────────────────────────

async def search_papers(query: str, sources: list[str] | None = None, filters: dict | None = None) -> list[SearchResult]:
    """Search DuckDuckGo + Google concurrently, return top-10 deduped results."""

    sources = sources or ["papers", "web"]
    filters = filters or {}
    
    # Use minCitations as the top K data count to fetch
    total_results = filters.get("minCitations", 10)
    if total_results <= 0:
        total_results = 10
    max_per_engine = total_results
    
    sites = []
    
    # Process papers database filters
    if "papers" in sources:
        db_papers = filters.get("dbPapers", {})
        if db_papers.get("arxiv"):
            sites.append("arxiv.org")
        if db_papers.get("pubmed"):
            sites.append("ncbi.nlm.nih.gov")
        if db_papers.get("clinicalTrials"):
            sites.append("clinicaltrials.gov")
        if db_papers.get("semanticScholar"):
            sites.append("semanticscholar.org")
            
        # Default academic sites if no specific DB is checked, or if we just want a broad academic search
        if not sites or (db_papers.get("semanticScholar") and db_papers.get("openAlex") and not db_papers.get("pubmed") and not db_papers.get("arxiv")):
            sites.extend(["scholar.google.com", "arxiv.org", "researchgate.net", "academia.edu", "ncbi.nlm.nih.gov", "jstor.org"])

    # Process web database filters
    if "web" in sources:
        db_web = filters.get("dbWeb", {})
        if db_web.get("gov"):
            sites.append(".gov")
        if db_web.get("edu"):
            sites.append(".edu")

    # Construct the final academic query
    academic_query = query
    
    pub_types = filters.get("pubTypes", {})
    if pub_types.get("review"):
        academic_query += ' "review"'
    if pub_types.get("preprint"):
        academic_query += ' "preprint"'
        
    dates = filters.get("dates", {})
    if dates.get("start"):
        academic_query += f' after:{dates["start"][:4]}'
    if dates.get("end"):
        academic_query += f' before:{dates["end"][:4]}'

    if sites:
        # Build OR'd site list: site:arxiv.org OR site:ncbi.nlm.nih.gov
        site_str = " OR ".join([f"site:{s}" for s in set(sites)])
        academic_query = f"{academic_query} {site_str}"
    else:
        academic_query = f"{academic_query} research paper thesis"

    try:
        ddg_raw, google_raw = await asyncio.wait_for(
            asyncio.gather(
                asyncio.to_thread(_ddg_sync, academic_query, max_per_engine),
                asyncio.to_thread(_google_sync, academic_query, max_per_engine),
                return_exceptions=True,
            ),
            timeout=TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.warning("Search timed out")
        return []

    if isinstance(ddg_raw, Exception):
        logger.warning(f"DDG gather error: {ddg_raw}")
        ddg_raw = []
    if isinstance(google_raw, Exception):
        logger.warning(f"Google gather error: {google_raw}")
        google_raw = []

    # Merge: DuckDuckGo first (has snippets), Google second
    seen: set[str] = set()
    merged: list[SearchResult] = []

    for raw_list in (ddg_raw, google_raw):
        for r in raw_list:
            url = (r.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            merged.append(SearchResult(
                index   = 0,          # assigned below
                title   = r.get("title") or "Untitled",
                url     = url,
                snippet = (r.get("snippet") or "")[:500],
                source  = r.get("source", "web"),
            ))
            if len(merged) >= total_results:
                break
        if len(merged) >= total_results:
            break

    # Assign 1-based indices
    for i, sr in enumerate(merged, start=1):
        sr.index = i

    return merged[:total_results]
