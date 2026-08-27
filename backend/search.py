"""Web search engine integration: DuckDuckGo + Google, run concurrently.

Both engines run in threads (asyncio.to_thread) so the FastAPI event
loop is never blocked. Results are merged and deduplicated by URL.

Upgrade (v2):
- Smart HTML extraction: prefers <article>, <main>, <section> tags
- User-Agent header to bypass lightweight bot-blocking
- 12 000-char content limit per source (was 6 000)
- Per-URL scrape progress callback for real-time SSE feedback
- Single retry on transient connection/SSL failures
- 10-second scrape timeout per URL (was 6 s)
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Awaitable
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from models import SearchResult

MAX_PER_ENGINE  = 8    # fetch a few extra so dedup still yields the target
TOTAL_RESULTS   = 8    # default top-N returned
SCRAPE_TIMEOUT  = 10.0 # seconds per URL
SCRAPE_MAX_CHARS = 12_000  # chars of page text fed to LLM per source
SEARCH_TIMEOUT  = 90   # seconds — must be long enough for DDG retry backoff (up to ~31s)

# Realistic browser User-Agent header
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


# ── Synchronous helpers (executed in thread-pool) ─────────────────────────────

import time
import random

_DDG_MAX_RETRIES   = 5   # how many times to retry DDG before giving up
_DDG_BASE_DELAY    = 1.0 # seconds — doubles each retry (exponential backoff)
_GOOGLE_MAX_RETRIES = 3
_BING_MAX_RETRIES  = 3

# Rotate query variants to bypass DDG rate-limits on repeated failures
_QUERY_SUFFIXES = ["", " research", " academic", " overview", " explained"]


def _ddg_sync(query: str, max_results: int) -> list[dict]:
    """
    DuckDuckGo text search with automatic retry + exponential backoff.
    Rotates query variants on each attempt so rate-limit blocks are bypassed.
    Never gives up silently — tries up to _DDG_MAX_RETRIES times.
    """
    from ddgs import DDGS

    last_exc: Exception | None = None
    for attempt in range(_DDG_MAX_RETRIES):
        # Rotate a small suffix to vary the query and dodge caching/rate-limits
        suffix = _QUERY_SUFFIXES[attempt % len(_QUERY_SUFFIXES)]
        varied_query = query + suffix if suffix else query

        try:
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(varied_query, max_results=max_results):
                    results.append({
                        "title":   r.get("title", ""),
                        "url":     r.get("href", ""),
                        "snippet": r.get("body", ""),
                        "source":  "duckduckgo",
                    })
            if results:
                if attempt > 0:
                    logger.info(f"DuckDuckGo succeeded on attempt {attempt + 1}")
                return results
            # Empty result — treat as soft failure and retry
            raise ValueError("No results found.")
        except Exception as exc:
            last_exc = exc
            delay = _DDG_BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
            logger.warning(
                f"DuckDuckGo attempt {attempt + 1}/{_DDG_MAX_RETRIES} failed: {exc} "
                f"— retrying in {delay:.1f}s…"
            )
            time.sleep(delay)

    logger.error(f"DuckDuckGo gave up after {_DDG_MAX_RETRIES} attempts: {last_exc}")
    return []


def _ddg_images_sync(query: str, max_results: int) -> list[str]:
    """DuckDuckGo image search with retry."""
    from ddgs import DDGS

    for attempt in range(3):
        try:
            images = []
            with DDGS() as ddgs:
                for r in ddgs.images(query, max_results=max_results):
                    url = r.get("image")
                    if url:
                        images.append(url)
            if images:
                return images
            raise ValueError("No images found.")
        except Exception as exc:
            delay = _DDG_BASE_DELAY * (2 ** attempt)
            logger.warning(f"DuckDuckGo images attempt {attempt + 1}/3 failed: {exc} — retrying in {delay:.1f}s…")
            time.sleep(delay)
    return []


def _google_sync(query: str, max_results: int) -> list[dict]:
    """Google search with retry using googlesearch-python (keyless scrape)."""
    for attempt in range(_GOOGLE_MAX_RETRIES):
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
            if results:
                if attempt > 0:
                    logger.info(f"Google search succeeded on attempt {attempt + 1}")
                return results
            raise ValueError("No results found.")
        except Exception as exc:
            delay = 2.0 * (attempt + 1)
            logger.warning(f"Google search attempt {attempt + 1}/{_GOOGLE_MAX_RETRIES} failed: {exc} — retrying in {delay:.1f}s…")
            time.sleep(delay)
    logger.error("Google search gave up after all retries.")
    return []


def _bing_sync(query: str, max_results: int) -> list[dict]:
    """
    Bing web search via HTML scraping — used as a third-engine fallback.
    No API key required. Retries up to _BING_MAX_RETRIES times.
    """
    import urllib.parse
    import re
    import requests as _req

    headers = {
        "User-Agent": _UA,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    }

    for attempt in range(_BING_MAX_RETRIES):
        try:
            encoded = urllib.parse.quote_plus(query)
            url = f"https://www.bing.com/search?q={encoded}&count={max_results}&setlang=en"
            resp = _req.get(url, headers=headers, timeout=15)
            resp.raise_for_status()

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")

            results = []
            for li in soup.select("li.b_algo")[:max_results]:
                a_tag = li.select_one("h2 a")
                snippet_tag = li.select_one(".b_caption p")
                if not a_tag:
                    continue
                href = a_tag.get("href", "")
                # Skip Bing redirect URLs — only accept direct HTTP(S) links
                if not href.startswith("http"):
                    continue
                results.append({
                    "title":   a_tag.get_text(strip=True),
                    "url":     href,
                    "snippet": snippet_tag.get_text(strip=True) if snippet_tag else "",
                    "source":  "bing",
                })

            if results:
                if attempt > 0:
                    logger.info(f"Bing search succeeded on attempt {attempt + 1}")
                return results
            raise ValueError("No results parsed from Bing HTML.")
        except Exception as exc:
            delay = 2.0 * (attempt + 1)
            logger.warning(f"Bing attempt {attempt + 1}/{_BING_MAX_RETRIES} failed: {exc} — retrying in {delay:.1f}s…")
            time.sleep(delay)

    logger.error("Bing search gave up after all retries.")
    return []


# ── Smart HTML text extractor ─────────────────────────────────────────────────

def _extract_text(html: bytes) -> str:
    """
    Extract the most content-rich text from raw HTML.

    Priority order:
      1. <article> — blog posts, papers, Wikipedia articles
      2. <main>    — standard semantic landmark
      3. <div id/class containing "content","article","body","post">
      4. Full page fallback (minus boilerplate tags)
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove boilerplate elements
    for tag in soup(["script", "style", "nav", "header", "footer",
                      "aside", "form", "noscript", "svg", "iframe"]):
        tag.decompose()

    # Try semantic / structural candidates first
    candidates = (
        soup.find("article")
        or soup.find("main")
        or soup.find(id=lambda v: v and any(k in v.lower() for k in ("content", "article", "body", "post", "entry")))
        or soup.find(class_=lambda v: v and any(k in " ".join(v).lower() for k in ("content", "article", "body", "post", "entry")))
    )

    root = candidates if candidates else soup.body or soup

    text = root.get_text(separator=" ", strip=True)
    # Collapse runs of whitespace
    import re
    text = re.sub(r"\s{2,}", " ", text)
    return text[:SCRAPE_MAX_CHARS]


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from a PDF file."""
    try:
        import pypdf
        import io
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text.append(page_text)
        
        full_text = " ".join(text)
        import re
        full_text = re.sub(r"\s{2,}", " ", full_text)
        return full_text[:SCRAPE_MAX_CHARS]
    except Exception as exc:
        logger.warning(f"PDF extraction failed: {exc}")
        return ""


# ── Async URL scraper with retry ──────────────────────────────────────────────

async def _scrape_url(url: str) -> str:
    """Fetch and extract main text from a URL. Retries once on failure."""
    if not url or not url.startswith("http"):
        return ""

    headers = {"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"}

    for attempt in range(2):  # try twice
        try:
            async with httpx.AsyncClient(
                verify=False,
                timeout=SCRAPE_TIMEOUT,
                follow_redirects=True,
                headers=headers,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()

                content_type = resp.headers.get("Content-Type", "").lower()
                
                if "application/pdf" in content_type or resp.content.startswith(b"%PDF"):
                    return _extract_pdf_text(resp.content)
                elif "text/html" in content_type or "text/plain" in content_type or not content_type:
                    return _extract_text(resp.content)
                else:
                    logger.debug(f"Skipping unsupported content type '{content_type}' for {url}")
                    return ""
        except Exception as exc:
            if attempt == 0:
                logger.debug(f"Scrape attempt 1 failed for {url}: {exc} — retrying…")
                await asyncio.sleep(0.5)
            else:
                logger.debug(f"Scrape failed for {url}: {exc}")
    return ""


# ── Public async function ──────────────────────────────────────────────────────

async def search_papers(
    query: str,
    sources: list[str] | None = None,
    filters: dict | None = None,
    progress_cb: Optional[Callable[[int, int, str], Awaitable[None]]] = None,
) -> list[SearchResult]:
    """
    Search DuckDuckGo + Google concurrently, scrape each result's full page,
    and return the top-N deduplicated results.

    Args:
        progress_cb: async callable(current, total, title) called after each
                     URL is scraped so the caller can stream SSE progress.
    """
    sources = sources or ["papers", "web"]
    filters = filters or {}

    # Determine how many results to fetch
    total_results = filters.get("minCitations", TOTAL_RESULTS)
    if total_results <= 0:
        total_results = TOTAL_RESULTS

    max_per_engine = total_results + 5

    sites: list[str] = []

    # Academic DB site filters
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

        # Default academic sites when no specific DB is checked
        if not sites or (
            db_papers.get("semanticScholar")
            and db_papers.get("openAlex")
            and not db_papers.get("pubmed")
            and not db_papers.get("arxiv")
        ):
            sites.extend([
                "scholar.google.com", "arxiv.org", "researchgate.net",
                "academia.edu", "ncbi.nlm.nih.gov", "jstor.org",
            ])

    # Web DB filters
    if "web" in sources:
        db_web = filters.get("dbWeb", {})
        if db_web.get("gov"):
            sites.append(".gov")
        if db_web.get("edu"):
            sites.append(".edu")

    # ── Build queries ─────────────────────────────────────────────────────────
    queries_to_run = []

    # 1. Academic query (if papers selected)
    if "papers" in sources:
        paper_query = query
        pub_types = filters.get("pubTypes", {})
        if pub_types.get("review"):
            paper_query += ' "review"'
        if pub_types.get("preprint"):
            paper_query += ' "preprint"'

        dates = filters.get("dates", {})
        if dates.get("start"):
            paper_query += f' after:{dates["start"][:4]}'
        if dates.get("end"):
            paper_query += f' before:{dates["end"][:4]}'

        # Filter to specific academic sites if any were selected
        academic_sites = [s for s in sites if not s.startswith(".")] # .gov, .edu are handled by web
        if academic_sites:
            site_str = " OR ".join([f"site:{s}" for s in set(academic_sites)])
            paper_query = f"{paper_query} {site_str}"
        else:
            paper_query = f"{paper_query} research paper thesis"

        queries_to_run.append(paper_query)

    # 2. Web query (if web selected)
    if "web" in sources:
        web_query = query
        web_sites = [s for s in sites if s.startswith(".")] # .gov, .edu
        
        # Check if we should restrict to specific web domains or allow all
        db_web = filters.get("dbWeb", {})
        if web_sites and not db_web.get("all", True):
            site_str = " OR ".join([f"site:{s}" for s in set(web_sites)])
            web_query = f"{web_query} {site_str}"
            
        queries_to_run.append(web_query)

    # If neither (shouldn't happen, but fallback)
    if not queries_to_run:
        queries_to_run.append(query)

    # ── Run search engines concurrently for all queries ─────────────────────
    tasks = []

    # DDG + Google + Bing for each query, images via DDG on the base query
    for q in queries_to_run:
        tasks.append(asyncio.to_thread(_ddg_sync, q, max_per_engine))
        tasks.append(asyncio.to_thread(_google_sync, q, max_per_engine))
        tasks.append(asyncio.to_thread(_bing_sync, q, max_per_engine))

    tasks.append(asyncio.to_thread(_ddg_images_sync, query, 3))

    try:
        results_gather = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=SEARCH_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("Search timed out")
        return []

    # The last task is the images, the rest are text searches
    text_results_raw = results_gather[:-1]
    ddg_images_raw = results_gather[-1]

    ddg_images = ddg_images_raw if not isinstance(ddg_images_raw, Exception) else []
    
    # ── Merge & dedup ──────────────────
    seen: set[str] = set()
    merged: list[SearchResult] = []

    for raw_list in text_results_raw:
        if isinstance(raw_list, Exception):
            logger.warning(f"Search gather error: {raw_list}")
            continue
            
        for r in raw_list:
            url = (r.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            merged.append(SearchResult(
                index   = 0,   # assigned below
                title   = r.get("title") or "Untitled",
                url     = url,
                snippet = (r.get("snippet") or "")[:500],
                source  = r.get("source", "web"),
            ))
            if len(merged) >= total_results:
                break
        if len(merged) >= total_results:
            break

    # Assign 1-based indices and distribute images
    img_idx = 0
    for i, sr in enumerate(merged, start=1):
        sr.index = i
        if img_idx < len(ddg_images) and img_idx < 3:
            sr.image_url = ddg_images[img_idx]
            img_idx += 1

    # ── Scrape each URL sequentially so we can emit per-URL progress ─────────
    total = len(merged[:total_results])
    for idx, sr in enumerate(merged[:total_results], start=1):
        logger.info(f"Scraping {idx}/{total}: {sr.url}")

        # Notify caller (SSE) before scraping starts for this URL
        if progress_cb:
            await progress_cb(idx, total, sr.title or sr.url or "")

        text = await _scrape_url(sr.url or "")
        if text:
            sr.full_text = text

    return merged[:total_results]
