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
from synthesizer import synthesize


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

            results: list[SearchResult] = await search_papers(req.query, req.sources, req.filters)

            if not results:
                yield _sse(StreamEventType.STAGE, {"message": "⚠️ No results found. Try a different query."})
                yield _sse(StreamEventType.DONE,  {"session_id": session_id})
                return

            # Emit top-10 results immediately so UI can show them
            yield _sse(
                StreamEventType.RESULT,
                {"results": [r.model_dump() for r in results]},
            )

            # Stage 2: synthesizing
            yield _sse(StreamEventType.STAGE, {"message": f"📝 Found {len(results)} papers. Generating synthesis paper…"})

            paper_text = ""
            async for token in synthesize(req.query, results):
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
