"""ThesisAI — FastAPI backend, port 8888.

Endpoints:
  GET  /health                        → liveness probe
  POST /api/query                     → SSE stream (stages + tokens + results)
  GET  /api/download/{session_id}     → download synthesised .txt paper
"""
from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, PlainTextResponse
from loguru import logger

import session_store
from models import QueryRequest, SearchResult, StreamEventType, SynthesisResult
from search import search_papers
from synthesizer import synthesize, suggest_alternative_topics


# ── App lifecycle ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    sweeper = asyncio.create_task(session_store.run_sweeper())
    logger.info("ThesisAI backend started on port 8888")
    yield
    sweeper.cancel()
    logger.info("ThesisAI backend shutting down")


app = FastAPI(title="ThesisAI", lifespan=lifespan)

# CORS — allow the Vite dev server on port 3333
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3333",
        "http://127.0.0.1:3333",
        "*",  # remove in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _sse(event_type: StreamEventType, data: dict) -> str:
    return f"data: {json.dumps({'type': event_type.value, **data})}\n\n"


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "ThesisAI", "port": 8888}


@app.post("/api/query")
async def query(req: QueryRequest):
    session_id = req.session_id or str(uuid.uuid4())

    async def event_stream():
        try:
            # Stage 1: searching
            yield _sse(StreamEventType.STAGE, {"message": "🔎 Searching"})

            # For follow-up queries, respect the selected sources
            results: list[SearchResult] = []

            # ── progress callback: emit per-URL scraping events ──────────
            # We accumulate SSE strings in yield_queue inside the callback
            # (which cannot yield directly) and drain it after each search call.
            yield_queue: list[str] = []

            async def _scrape_progress(current: int, total: int, title: str) -> None:
                label = (title[:60] + "…") if len(title) > 60 else title
                yield_queue.append(_sse(
                    StreamEventType.SCRAPING,
                    {"current": current, "total": total, "title": label},
                ))

            if req.is_followup:
                if "web" in req.sources:
                    yield _sse(StreamEventType.STAGE, {"message": "🔎 Searching the internet for follow-up..."})
                    search_q = f"{req.original_query} {req.query}" if req.original_query else req.query
                    results = await search_papers(search_q, ["web"], req.filters, _scrape_progress)
                    # drain scraping progress events
                    for ev in yield_queue:
                        yield ev
                    yield_queue.clear()

                if "papers" not in req.sources:
                    req.thesis_context = None

                if not results and not req.thesis_context:
                    err_msg = "> [!WARNING]\n> **No sources selected.**\n> Please select at least one source (Papers or Internet) for your follow-up query.\n\n"
                    yield _sse(StreamEventType.TOKEN, {"content": err_msg})
                    yield _sse(StreamEventType.DONE, {"session_id": session_id})
                    return
            else:
                yield _sse(StreamEventType.STAGE, {"message": "🔎 Searching for top sources..."})
                results = await search_papers(req.query, req.sources, req.filters, _scrape_progress)
                # drain scraping progress events
                for ev in yield_queue:
                    yield ev
                yield_queue.clear()

                if not results:
                    err_msg = "> [!WARNING]\n> **No sources found.**\n> Please provide a more elaborate or specific query to search.\n\n"

                    suggestions = await suggest_alternative_topics(req.query)
                    if suggestions:
                        err_msg += "**Alternatively, try exploring one of these related topics:**\n\n"
                        for s in suggestions:
                            err_msg += f"- *{s}*\n"

                    yield _sse(StreamEventType.TOKEN, {"content": err_msg})
                    await session_store.save(SynthesisResult(
                        session_id=session_id, query=req.query, results=[], paper_text=err_msg
                    ))
                    yield _sse(StreamEventType.DONE, {"session_id": session_id})
                    return

            if results:
                # Emit results immediately so UI can show source cards
                yield _sse(
                    StreamEventType.RESULT,
                    {"results": [r.model_dump() for r in results]},
                )

            # Stage 3: synthesizing
            if req.is_followup:
                msg = "💡 Generating response..." if not results else f"💡 Found {len(results)} new sources. Generating response..."
                yield _sse(StreamEventType.STAGE, {"message": msg})
            else:
                yield _sse(StreamEventType.STAGE, {"message": f"📝 Analysing {len(results)} sources. Writing thesis…"})

            paper_text = ""
            async for token in synthesize(req.query, results, is_followup=req.is_followup, thesis_context=req.thesis_context):
                paper_text += token
                yield _sse(StreamEventType.TOKEN, {"content": token})

            # Save to session store for download
            await session_store.save(SynthesisResult(
                session_id = session_id,
                query      = req.query,
                results    = results,
                paper_text = paper_text,
            ))

            yield _sse(StreamEventType.DONE, {"session_id": session_id})

        except Exception as exc:
            logger.exception("Query pipeline error")
            yield _sse(StreamEventType.ERROR, {"message": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/download/{session_id}")
async def download(session_id: str):
    result = await session_store.get(session_id)
    if not result:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    safe_query = "".join(c if c.isalnum() or c in " _-" else "_" for c in result.query)[:50]
    filename   = f"ThesisAI_{safe_query}.txt".replace(" ", "_")

    return PlainTextResponse(
        content    = result.paper_text,
        headers    = {"Content-Disposition": f'attachment; filename="{filename}"'},
        media_type = "text/plain; charset=utf-8",
    )
