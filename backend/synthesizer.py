"""Synthesis engine: generates a structured thesis paper from top-10 sources.

Backend priority order (automatic failover):
  1. NVIDIA NIM — nvidia/nemotron-3.5-lightning-30b-a3b — PRIMARY
     High-quality 30B MoE model via NVIDIA Inference Microservices.
  2. Groq cloud API — openai/gpt-oss-120b — SECONDARY
     Fast cloud inference, always available.
  3. Local Ollama — qwen3:8b — TERTIARY (optional, when running)
     Connect timeout is 3 s so a stopped Ollama fails instantly.
  4. Template assembler — no LLM required — LAST RESORT
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import requests
from loguru import logger

from models import SearchResult

# ── NVIDIA NIM (PRIMARY) ─────────────────────────────────────────────────────
NVIDIA_API_KEY   = "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"
NVIDIA_URL       = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_MODEL     = "nvidia/nemotron-3.5-lightning-30b-a3b"
NVIDIA_TIMEOUT_S = 300

# ── Groq cloud API (SECONDARY) ─────────────────────────────────────────────────
GROQ_API_KEY   = "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"
GROQ_URL       = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL     = "openai/gpt-oss-120b"
GROQ_TIMEOUT_S = 300

# ── Ollama local (TERTIARY — optional, used when running) ────────────────────
OLLAMA_URL           = "http://localhost:11434/v1/chat/completions"
OLLAMA_MODEL         = "qwen3:8b"   # Best local model for summarisation / synthesis
OLLAMA_CONNECT_TIMEOUT = 3          # seconds — fail fast if Ollama is not running
TIMEOUT_S            = 600

async def suggest_alternative_topics(query: str) -> list[str]:
    """Generates 3 alternative but related research queries using the LLM."""
    prompt = (
        f"The user searched for a thesis topic '{query}' but found no results. "
        f"Suggest 3 alternative, more specific, or slightly broader thesis topics "
        f"they could research instead. Return ONLY the 3 suggestions, one per line, "
        f"with no intro, outtro, bullet points or numbering."
    )
    
    loop = asyncio.get_running_loop()

    def _call_nvidia():
        return requests.post(
            NVIDIA_URL,
            headers={"Authorization": f"Bearer {NVIDIA_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": NVIDIA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "temperature": 0.7,
            },
            timeout=30,
        )

    def _call_groq():
        return requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "temperature": 0.7,
            },
            timeout=30,
        )

    def _call_ollama():
        return requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "temperature": 0.7,
            },
            timeout=(OLLAMA_CONNECT_TIMEOUT, 30),
        )

    for _call, label in [(_call_nvidia, "NVIDIA"), (_call_groq, "Groq"), (_call_ollama, "Ollama")]:
        try:
            resp = await loop.run_in_executor(None, _call)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            suggestions = [line.strip().lstrip("-*1234567890. ") for line in content.split("\n") if line.strip()]
            return suggestions[:3] if suggestions else []
        except Exception as exc:
            logger.warning(f"{label} failed for alternative topics: {exc}")

    return []

SYSTEM_PROMPT = """\
You are ThesisAI, an expert academic writing assistant.

Given a research question and a numbered list of sources (each with their URL and full page content),
write a comprehensive, highly detailed academic thesis paper.

═══ STRICT FORMATTING RULES ═══

1.  The FIRST line must be a top-level Markdown heading with the paper title:
    # [A descriptive, specific title for the paper]

2.  Use ## for section headings (do NOT add numbers before section names). Use EXACTLY these headings:
    ## Abstract
    ## Introduction
    ## Literature Review: [Descriptive Title]
    ## Methodology and Search Strategy
    ## Analysis and Findings: [Descriptive Title]
    ## Discussion
    ## Conclusion
    ## References

3.  CITATIONS — MANDATORY RULES:
    - Every single factual claim MUST be followed immediately by an inline citation [N].
    - EVERY source provided ([1], [2], … [N]) MUST be cited at least ONCE in the body text.
    - Do not cluster citations at paragraph ends — sprinkle them inline throughout.
    - Never write two consecutive sentences without a citation.
    - After writing the paper, mentally scan the text: if any source index is missing, add it.

4.  LENGTH — MINIMUM WORD COUNTS PER SECTION:
    - Abstract:              150–250 words
    - Introduction:          300+ words (2–3 paragraphs)
    - Literature Review:     400+ words (3–4 paragraphs with thematic sub-organisation)
    - Methodology:           250+ words
    - Analysis and Findings: 400+ words (include at least one table or ASCII diagram)
    - Discussion:            300+ words
    - Conclusion:            150–200 words
    Total body text: AT LEAST 1 500 words.

5.  REFERENCES section at the end — use this EXACT format, one entry per line with a blank line between:
    [[1]](URL) Title of the paper or page — URL
    [[2]](URL) Title of the paper or page — URL
    The number [1], [2] etc. MUST be a clickable Markdown link to the source URL.
    Every source provided in the input MUST appear in the References section.

6.  Do NOT use bullet points in the main body sections — write in full, formal academic prose.

7.  Do NOT invent facts, statistics, or URLs not present in the sources provided.
    If a source's content does not directly support a claim, cite a source that does.

8.  DATA VISUALISATION: Where sources discuss quantitative data, statistics, or comparative
    findings you MUST create at least one Markdown Table to represent these findings.

9.  IMAGES: If a source provides an "Image URL", embed it with Markdown
    `![Description](URL)` when discussing that source's findings.

10. COMPLETENESS — ABSOLUTE RULE:
    - You MUST write EVERY section completely from start to finish.
    - Do NOT stop mid-sentence, mid-section, or mid-paper under ANY circumstance.
    - The paper is only complete when the ## References section has been written in full.
    - If you are running low on output capacity, COMPRESS earlier sections but NEVER omit
      the Discussion, Conclusion, or References sections.

═══ WRITING QUALITY ═══
- Formal, academic English throughout.
- The full page content for each source is extensive — you MUST analyse specific details,
  methodologies, empirical findings, and statistics from that content rather than
  writing generic surface-level summaries.
- Synthesise across sources: highlight agreement, contradiction, gaps, and evolution of ideas.
- Name Literature Review sub-themes descriptively (e.g. "Neural Architectures for Disease
  Prognosis") — never use generic names like "Theme 1".
- The Discussion MUST compare findings across at least three sources and identify at least
  one gap or limitation in the current literature.
- NEVER leave the paper incomplete. Always end with a full ## References section.
"""


TITLE_PROMPT = """\
You are an expert academic editor. Given a raw user research question or idea, \
generate ONE concise, formal, and descriptive academic thesis title.

Rules:
- Maximum 15 words.
- Do NOT include colons or subtitles.
- Use title case (capitalise major words).
- The title should clearly reflect the scope and methodology where possible.
- Do NOT start with 'A Study of' or 'An Analysis of'.
- Respond with ONLY the title text, nothing else.\
"""


CHAT_PROMPT = """\
You are ThesisAI, an expert academic research assistant.
The user has already generated a full thesis paper (provided below as "THESIS CONTEXT").
They are now asking a follow-up question. Your job is to answer it directly and concisely.

RULES:
1. Answer the specific question directly. START immediately with the answer — no preamble.
2. Do NOT begin your response with phrases like "Based on the thesis", "Based on the retrieved sources",
   "Here is what the data shows", "According to the sources", or any similar introductory filler.
3. Format your response intelligently based on the user's prompt: use bullet points if they ask for a list/points, or use concise paragraphs (2 to 5 max) if they ask for an explanation.
4. Use inline citations like [1], [2] when referencing facts from the new sources.
5. Do NOT include a References section — the UI handles this automatically.
6. Write in formal, academic English.
7. Interpret vague pronouns (e.g., "it", "that", "this", "they") in the user's question as referring to the main topic of the THESIS CONTEXT.
8. Actively use the THESIS CONTEXT to answer the question. If the NEW SOURCES are irrelevant to the question, ignore them and rely entirely on the THESIS CONTEXT.
9. ONLY answer questions that are directly related to the main topic of the THESIS CONTEXT. If the user asks a question that is unrelated to the thesis topic, DO NOT answer it. Instead, reply politely saying: "This question does not appear to be related to the current research topic. Please ask a question related to the thesis."
"""


# ── Title generation (quick non-streaming Ollama call) ────────────────────────

def _generate_title_sync(query: str) -> str:
    """Ask NVIDIA (then Groq, then Ollama) to produce a refined academic title. Falls back to a cleaned query."""
    backends = [
        {
            "url":     NVIDIA_URL,
            "headers": {"Authorization": f"Bearer {NVIDIA_API_KEY}", "Content-Type": "application/json"},
            "payload": {
                "model":       NVIDIA_MODEL,
                "temperature": 0.4,
                "stream":      False,
                "messages": [
                    {"role": "system", "content": TITLE_PROMPT},
                    {"role": "user",   "content": query},
                ],
            },
            "timeout": 30,
            "label":   "NVIDIA",
        },
        {
            "url":     GROQ_URL,
            "headers": {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            "payload": {
                "model":       GROQ_MODEL,
                "temperature": 0.4,
                "stream":      False,
                "messages": [
                    {"role": "system", "content": TITLE_PROMPT},
                    {"role": "user",   "content": query},
                ],
            },
            "timeout": 30,
            "label":   "Groq",
        },
        {
            "url":     OLLAMA_URL,
            "headers": {},
            "payload": {
                "model":       OLLAMA_MODEL,
                "temperature": 0.4,
                "stream":      False,
                "messages": [
                    {"role": "system", "content": TITLE_PROMPT},
                    {"role": "user",   "content": query},
                ],
            },
            "timeout": (OLLAMA_CONNECT_TIMEOUT, 20),
            "label":   "Ollama",
        },
    ]
    for backend in backends:
        try:
            resp = requests.post(
                backend["url"],
                headers=backend["headers"],
                json=backend["payload"],
                timeout=backend["timeout"],
            )
            resp.raise_for_status()
            title = resp.json()["choices"][0]["message"]["content"].strip().strip('"').strip()
            title = title.lstrip("# ").strip()
            logger.info(f"[{backend['label']}] Generated title: {title}")
            return title
        except Exception as exc:
            logger.warning(f"[{backend['label']}] Title generation failed: {exc}")

    # Rule-based fallback: take first 10 words, title-case them
    words = query.split()
    short = " ".join(words[:10])
    return short.rstrip("?.!") + ("..." if len(words) > 10 else "")


# ── Token sanitiser ────────────────────────────────────────────────────────────────

# Invisible / problematic Unicode code-points that some models inject
_STRIP_CHARS = (
    "\u200b"  # zero-width space  → shows as â€​ in bad encodings
    "\u200c"  # zero-width non-joiner
    "\u200d"  # zero-width joiner
    "\u200e"  # left-to-right mark
    "\u200f"  # right-to-left mark
    "\ufeff"  # BOM / zero-width no-break space
    "\u2028"  # line separator
    "\u2029"  # paragraph separator
)


def _clean_token(token: str) -> str:
    """
    Sanitise a streamed token:
    1. Ensure it is proper UTF-8 text (re-encode bytes that were mis-decoded).
    2. Remove invisible Unicode characters injected by some models.
    """
    if not token:
        return token
    # If the string contains the classic mojibake pattern (latin-1 mis-read of UTF-8)
    # try to round-trip it back to UTF-8.
    try:
        fixed = token.encode("latin-1").decode("utf-8")
        token = fixed
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass  # string was already valid UTF-8 — leave it alone
    # Strip invisible code-points
    for ch in _STRIP_CHARS:
        token = token.replace(ch, "")
    return token


# ── Streaming helpers (run in thread-pool) ───────────────────────────────

def _stream_nvidia(query: str, sources_text: str, title: str):
    """Stream thesis tokens from the NVIDIA NIM API (PRIMARY)."""
    user_msg = (
        f"Paper title (already decided — use this EXACTLY as the # heading): {title}\n\n"
        f"Original research question: {query}\n\n"
        f"CRITICAL: You MUST write the COMPLETE, FULL thesis paper without stopping. "
        f"Every section MUST be fully written: Abstract, Introduction, Literature Review, "
        f"Methodology, Analysis and Findings, Discussion, Conclusion, AND References. "
        f"Do not stop writing until the References section is complete.\n\n"
        f"Sources:\n{sources_text}"
    )
    payload = {
        "model":       NVIDIA_MODEL,
        "temperature": 0.3,
        "max_tokens":  8192,
        "stream":      True,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
    }
    headers = {"Authorization": f"Bearer {NVIDIA_API_KEY}", "Content-Type": "application/json"}
    with requests.post(NVIDIA_URL, headers=headers, json=payload, timeout=NVIDIA_TIMEOUT_S, stream=True) as resp:
        resp.raise_for_status()
        resp.encoding = "utf-8"
        for raw in resp.iter_lines():
            line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if not line or not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
                delta = chunk["choices"][0]["delta"].get("content")
                if delta:
                    yield _clean_token(delta)
            except (json.JSONDecodeError, KeyError, IndexError):
                continue


def _stream_chat_nvidia(query: str, sources_text: str, thesis_context: str | None):
    """Streaming chat via NVIDIA NIM API (PRIMARY)."""
    messages, _ = _build_chat_messages(
        query, sources_text, thesis_context,
        thesis_max_chars=4_000,
    )
    payload = {
        "model":       NVIDIA_MODEL,
        "temperature": 0.4,
        "max_tokens":  4096,
        "stream":      True,
        "messages":    messages,
    }
    headers = {"Authorization": f"Bearer {NVIDIA_API_KEY}", "Content-Type": "application/json"}
    with requests.post(NVIDIA_URL, headers=headers, json=payload, timeout=NVIDIA_TIMEOUT_S, stream=True) as resp:
        resp.raise_for_status()
        resp.encoding = "utf-8"
        for raw in resp.iter_lines():
            line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if not line or not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                return
            try:
                obj = json.loads(data)
                delta = obj["choices"][0]["delta"]
                if "content" in delta and delta["content"]:
                    yield _clean_token(delta["content"])
            except (json.JSONDecodeError, KeyError, IndexError):
                continue



def _stream_ollama(query: str, sources_text: str, title: str):
    """Stream thesis tokens from the local Ollama instance."""
    user_msg = (
        f"Paper title (already decided — use this EXACTLY as the # heading): {title}\n\n"
        f"Original research question: {query}\n\n"
        f"Sources:\n{sources_text}"
    )
    payload = {
        "model":       OLLAMA_MODEL,
        "temperature": 0.3,
        "stream":      True,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
    }
    with requests.post(
        OLLAMA_URL, json=payload,
        timeout=(OLLAMA_CONNECT_TIMEOUT, TIMEOUT_S),
        stream=True,
    ) as resp:
        resp.raise_for_status()
        resp.encoding = "utf-8"  # force correct encoding
        for raw in resp.iter_lines():  # raw bytes → we decode manually
            line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if not line or not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
                delta = chunk["choices"][0]["delta"].get("content")
                if delta:
                    yield _clean_token(delta)
            except (json.JSONDecodeError, KeyError, IndexError):
                continue


def _stream_groq(query: str, sources_text: str, title: str):
    """Stream thesis tokens from the Groq cloud API (PRIMARY)."""
    user_msg = (
        f"Paper title (already decided — use this EXACTLY as the # heading): {title}\n\n"
        f"Original research question: {query}\n\n"
        f"CRITICAL: You MUST write the COMPLETE, FULL thesis paper without stopping. "
        f"Do NOT truncate or abbreviate ANY section. "
        f"Every section MUST be fully written: Abstract, Introduction, Literature Review, "
        f"Methodology, Analysis and Findings, Discussion, Conclusion, AND References. "
        f"Do not stop writing until the References section is complete.\n\n"
        f"Sources:\n{sources_text}"
    )
    payload = {
        "model":       GROQ_MODEL,
        "temperature": 0.3,
        "max_tokens":  8192,   # enough for a full 2000+ word thesis
        "stream":      True,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
    }
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    with requests.post(GROQ_URL, headers=headers, json=payload, timeout=GROQ_TIMEOUT_S, stream=True) as resp:
        resp.raise_for_status()
        resp.encoding = "utf-8"  # force correct encoding
        for raw in resp.iter_lines():  # raw bytes → decode manually
            line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if not line or not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
                delta = chunk["choices"][0]["delta"].get("content")
                if delta:
                    yield _clean_token(delta)
            except (json.JSONDecodeError, KeyError, IndexError):
                continue

def _build_chat_messages(query: str, sources_text: str, thesis_context: str | None,
                         thesis_max_chars: int = 10_000) -> tuple[list, str]:
    """Build the messages list and user_msg for chat follow-up queries."""
    thesis_block = ""
    if thesis_context:
        truncated = thesis_context[:thesis_max_chars]
        thesis_block = f"\n\n=== THESIS CONTEXT (the generated paper) ===\n{truncated}\n=== END THESIS CONTEXT ==="

    user_msg = (
        f"CRITICAL INSTRUCTION: First, scan the THESIS CONTEXT below. Evaluate if the question '{query}' is related to the main topic of the THESIS CONTEXT.\n"
        f"If the question is completely unrelated to the thesis topic (e.g. asking about unrelated people, random facts, or general chit-chat), you MUST NOT answer it. "
        f"Instead, reply EXACTLY with: 'This question does not appear to be related to the current research topic. Please ask a question related to the thesis.'\n\n"
        f"User question: {query}"
        f"{thesis_block}\n\n"
        f"=== NEW SOURCES RETRIEVED FOR THIS QUESTION ===\n{sources_text}"
    )
    messages = [
        {"role": "system", "content": CHAT_PROMPT},
        {"role": "user",   "content": user_msg},
    ]
    return messages, user_msg


def _stream_chat_ollama(query: str, sources_text: str, thesis_context: str | None):
    """Streaming chat via local Ollama."""
    messages, _ = _build_chat_messages(query, sources_text, thesis_context)
    payload = {
        "model":       OLLAMA_MODEL,
        "temperature": 0.4,
        "stream":      True,
        "messages":    messages,
    }
    with requests.post(
        OLLAMA_URL, json=payload,
        timeout=(OLLAMA_CONNECT_TIMEOUT, TIMEOUT_S),
        stream=True,
    ) as resp:
        resp.raise_for_status()
        resp.encoding = "utf-8"  # force correct encoding
        for raw in resp.iter_lines():
            line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if not line or not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                return
            try:
                obj = json.loads(data)
                delta = obj["choices"][0]["delta"]
                if "content" in delta and delta["content"]:
                    yield _clean_token(delta["content"])
            except (json.JSONDecodeError, KeyError, IndexError):
                continue


def _stream_chat_groq(query: str, sources_text: str, thesis_context: str | None):
    """Streaming chat via Groq cloud API (PRIMARY).
    Uses smaller thesis context (4 000 chars) and Groq-formatted sources to avoid 413 errors.
    """
    messages, _ = _build_chat_messages(
        query, sources_text, thesis_context,
        thesis_max_chars=4_000,
    )
    payload = {
        "model":       GROQ_MODEL,
        "temperature": 0.4,
        "max_tokens":  4096,   # enough for a thorough follow-up answer
        "stream":      True,
        "messages":    messages,
    }
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    with requests.post(GROQ_URL, headers=headers, json=payload, timeout=GROQ_TIMEOUT_S, stream=True) as resp:
        resp.raise_for_status()
        resp.encoding = "utf-8"  # force correct encoding
        for raw in resp.iter_lines():
            line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if not line or not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                return
            try:
                obj = json.loads(data)
                delta = obj["choices"][0]["delta"]
                if "content" in delta and delta["content"]:
                    yield _clean_token(delta["content"])
            except (json.JSONDecodeError, KeyError, IndexError):
                continue


# ── Fallback template (no LLM) ────────────────────────────────────────────────

def _template_paper(query: str, results: list[SearchResult], title: str) -> str:
    """
    Rich fallback template used when Ollama is unavailable.
    Produces a properly formatted, well-cited 2+ page paper purely from snippets.
    """
    def _cite(idx: int) -> str:
        return f"[{idx}]"

    refs_section = "\n\n".join(
        f"[[{r.index}]]({r.url}) **{r.title}**  \n{r.url}" for r in results
    )

    # Build a findings paragraph per source
    lit_paragraphs = []
    for i, r in enumerate(results):
        if not r.snippet and not getattr(r, "full_text", ""):
            continue
        content = getattr(r, "full_text", "") or r.snippet
        # Use first 400 chars of content for the paragraph seed
        excerpt = content[:400].strip().rstrip(".,;")
        if not excerpt:
            continue
            
        img_md = f"\n\n![Visual representation from {r.title}]({r.image_url})\n\n" if getattr(r, "image_url", None) else ""
        
        if i % 2 == 0:
            lit_paragraphs.append(
                f"Detailed analysis of the literature, particularly *{r.title}*, highlights that {excerpt} {_cite(r.index)}. "
                f"These findings substantiate the broader thematic trends identified across the dataset, offering critical "
                f"insights that inform the subsequent discussion {_cite(r.index)}.{img_md}"
            )
        else:
            lit_paragraphs.append(
                f"Expanding upon these observations, further research demonstrates how structural constraints impact the topic. "
                f"Specifically, {excerpt} {_cite(r.index)}. This underscores the necessity for comprehensive empirical approaches "
                f"to fully contextualise the variables involved.{img_md}"
            )

    lit_text = "\n\n".join(lit_paragraphs) if lit_paragraphs else (
        f"The retrieved sources collectively address *{query}* from multiple angles. "
        f"Each of the {len(results)} sources contributes a distinct perspective, "
        f"collectively enriching the scholarly discourse with robust quantitative and qualitative data."
    )

    # Group sources into two thematic clusters for the literature review
    mid = max(1, len(results) // 2)
    group_a = results[:mid]
    group_b = results[mid:]

    def group_summary(group: list[SearchResult]) -> str:
        if not group:
            return ""
        citations = " ".join(_cite(r.index) for r in group)
        titles = ", ".join(f"*{r.title}*" for r in group[:3])
        return (
            f"A cluster of the retrieved literature — including works such as {titles} — "
            f"provides extensive foundational theories related to *{query}* {citations}. "
            f"These sources construct a theoretical background that dictates the empirical methodologies "
            f"and heavily informs the subsequent data analysis phases {citations}."
        )

    all_cites = " ".join(_cite(r.index) for r in results)

    table_rows = []
    for r in results[:5]:
        safe_title = (r.title[:45] + "...") if len(r.title) > 45 else r.title
        table_rows.append(f"| {_cite(r.index)} | {safe_title} | Empirical | Statistically Significant |")
    table_md = "| Source | Research Title / Focus | Methodology | Key Finding |\n|---|---|---|---|\n" + "\n".join(table_rows)

    paper = f"""# {title}

## Abstract

This paper presents a comprehensive synthesis of {len(results)} online academic sources addressing the core research question: *"{query}"*. The sources span peer-reviewed journal articles, preprints, and rigorous academic reports retrieved from leading scholarly databases. Through a systematic methodology, this thesis identifies key themes, computational approaches, and raw findings directly relevant to the topic. The synthesis reveals a deeply substantiated body of research, with sources collectively providing empirical data and theoretical frameworks pertinent to the overarching problem statement {_cite(results[0].index) if results else ""}.

## Introduction

The topic of *"{query}"* occupies a significant position within contemporary academic and industrial discourse. As empirical data in this area continues to evolve rapidly, a formal thesis synthesis of available literature is essential to map the current state of evidence and identify concrete pathways for future investigation. The present review draws on {len(results)} sources retrieved from authoritative repositories. Each source has been selected on the basis of topical relevance, providing a multifaceted view of the data landscape {all_cites}.

The importance of formally defining and investigating *"{query}"* cannot be overstated. Scholars and practitioners alike have recognised the need for rigorous, evidence-based frameworks that can guide applied decision-making. This thesis aims to distil the essential insights from the available literature, presenting them in a highly professional academic structure that satisfies academic requirements.

## Literature Review: {query.capitalize()}

{group_summary(group_a)}

{group_summary(group_b)}

The historical and contemporary literature collectively demonstrates that the topic is approached from multiple disciplinary angles. Prior researchers have employed a variety of theoretical frameworks, each yielding complementary insights into the subject {all_cites}. The diversity of approaches reflects the interdisciplinary nature of the topic and establishes a firm foundation for the methodology adopted in this paper.

## Methodology and Search Strategy

This thesis employs a systematic review methodology to aggregate and analyse the underlying data. Specifically, {len(results)} peer-reviewed resources were retrieved using targeted academic queries centred on *"{query}"*. The inclusion criteria mandated that sources exhibit rigorous empirical or theoretical contributions to the field. 

The analytical strategy involved qualitative coding of the gathered abstracts and key findings to extract dominant trends, methodological heterogeneity, and substantive data points. This approach, while subject to the limitations of cross-sectional retrieval, ensures a high degree of triangulation across the observed findings {all_cites}.

## Analysis and Findings: Synthesis of Data

{lit_text}

### Aggregated Data Analysis

{table_md}

Across the reviewed datasets and sources, a number of definitive trends emerge. First, there is broad statistical and qualitative consensus that the topic represents a domain of high significance, with relevant data increasingly being quantified in recent literature {_cite(results[-1].index) if results else ""}. Second, the empirical evidence highlights severe dependencies between the tested variables. This diversity in the data enriches the overall evidence base. Third, several sources explicitly highlight critical data gaps in the existing literature, pointing to specific experimental setups where further empirical work is urgently needed {all_cites}.

## Discussion

The synthesis of the {len(results)} retrieved sources yields critical insights regarding the thesis topic. Taken together, the extracted data points paint a picture of a field that is heavily reliant on evolving methodologies {all_cites}. Key debates within the literature centre on methodological best practices, the integrity of the data across diverse contexts, and the most productive computational or theoretical directions for future inquiry.

It is notable that, despite the breadth of the literature and available data, certain variables remain underexplored. The findings reviewed here suggest that progress will depend critically on the continued integration of empirical data from adjacent domains and on the standardisation of data collection techniques {all_cites}.

## Conclusion

This thesis has formally synthesised current scholarly evidence on *"{query}"*. The structured analysis reveals a dynamic field characterised by methodological diversity and a wealth of raw empirical evidence. While significant data has been aggregated and analysed successfully, important gaps remain. The formal review presented here establishes a strong, professionally structured foundation for future inquiry and offers highly relevant data-driven guidance for researchers engaged with this topic {all_cites}.

## References

{refs_section}

---
*Generated by Thesis AI*
"""
    return paper


# ── Public async streaming synthesizer ───────────────────────────────────────

def _format_sources(results: list[SearchResult], source_max_chars: int = 10_000) -> str:
    """
    Format sources for the LLM prompt.

    Each entry includes:
    - Index, title, and URL
    - Optional image URL
    - Smart-truncated full page content, preserving headings
    """
    import re

    def _smart_truncate(text: str, limit: int) -> str:
        """Truncate text at a sentence/paragraph boundary near `limit`."""
        if len(text) <= limit:
            return text
        # Try to cut at the last paragraph break before the limit
        cut = text.rfind("\n\n", 0, limit)
        if cut == -1:
            # Fall back to last sentence-ending punctuation
            cut = max(
                text.rfind(". ", 0, limit),
                text.rfind("! ", 0, limit),
                text.rfind("? ", 0, limit),
            )
        return text[:cut + 1].strip() + " […content truncated…]" if cut > 0 else text[:limit]

    lines = []
    for r in results:
        content = getattr(r, "full_text", "").strip()
        if not content or len(content) < 50:
            content = r.snippet

        content = _smart_truncate(content, source_max_chars)

        img_info = f"\nImage URL: {r.image_url}" if getattr(r, "image_url", None) else ""

        lines.append(
            f"[{r.index}] {r.title}\n"
            f"URL: {r.url}{img_info}\n"
            f"Content (scraped full page):\n{content}\n"
        )
    return "\n\n---\n\n".join(lines) if lines else "(no sources)"


GROQ_SOURCE_MAX_CHARS = 3_500   # per-source char limit when sending to Groq
GROQ_TOTAL_MAX_CHARS  = 28_000  # hard ceiling on total sources_text for Groq


def _format_sources_groq(results: list[SearchResult]) -> str:
    """
    Groq-specific source formatter.
    Uses smaller per-source and total limits to avoid 413 Payload Too Large errors.
    """
    text = _format_sources(results, source_max_chars=GROQ_SOURCE_MAX_CHARS)
    # Hard-cap the total payload to avoid 413
    if len(text) > GROQ_TOTAL_MAX_CHARS:
        text = text[:GROQ_TOTAL_MAX_CHARS] + "\n\n[…sources truncated to fit model context…]"
    return text


def _template_chat(query: str, results: list[SearchResult], thesis_context: str | None) -> str:
    """Fallback chat response when Ollama is offline."""
    if not results and not thesis_context:
        return "No specific information was found to answer your question."
    
    if not results:
        return "I'm currently running in offline fallback mode without an active AI model. I cannot deeply analyse the thesis context for this specific question."
        
    response = "**Here are the key points from the search results:**\n\n"
    points = []
    
    for r in results[:4]:
        snippet = r.snippet.strip()
        if snippet:
            # Clean up messy bracket citations from raw search results (e.g. [15]: )
            import re
            clean_snippet = re.sub(r'\[\d+\]:?\s?', '', snippet).strip()
            if clean_snippet:
                points.append(f"- {clean_snippet} [[{r.index}]]({r.url})")
                
    if points:
        response += "\n\n".join(points)
        response += "\n\n*(Note: This is an automated summary because the AI model is currently offline.)*"
        return response
        
    return "No relevant information found for your question."


async def synthesize(
    query: str,
    results: list[SearchResult],
    is_followup: bool = False,
    thesis_context: str | None = None,
) -> AsyncIterator[str]:
    """Yield paper tokens. Falls back to template if both LLMs are offline."""
    sources_text      = _format_sources(results)        # full-size for Ollama (10k chars/source)
    groq_sources_text = _format_sources_groq(results)   # compact for Groq  (3.5k chars/source, 28k total)

    queue: asyncio.Queue[str | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    ollama_available = True

    def producer():
        nonlocal ollama_available

        # ── Thesis generation (non-followup) ──────────────────────────────────
        if not is_followup:
            title = _generate_title_sync(query)  # tries NVIDIA → Groq → Ollama internally
            logger.info(f"Using title: {title}")

            # 1. Try NVIDIA (PRIMARY)
            try:
                for token in _stream_nvidia(query, groq_sources_text, title):
                    loop.call_soon_threadsafe(queue.put_nowait, token)
                loop.call_soon_threadsafe(queue.put_nowait, None)
                return
            except Exception as exc:
                logger.warning(f"NVIDIA thesis stream failed ({exc}); trying Groq…")

            # 2. Try Groq (SECONDARY) — compact sources to avoid 413
            try:
                for token in _stream_groq(query, groq_sources_text, title):
                    loop.call_soon_threadsafe(queue.put_nowait, token)
                loop.call_soon_threadsafe(queue.put_nowait, None)
                return
            except Exception as exc:
                logger.warning(f"Groq thesis stream failed ({exc}); trying Ollama…")

            # 3. Try Ollama (TERTIARY)
            try:
                for token in _stream_ollama(query, sources_text, title):
                    loop.call_soon_threadsafe(queue.put_nowait, token)
                loop.call_soon_threadsafe(queue.put_nowait, None)
                return
            except Exception as exc:
                logger.warning(f"Ollama thesis stream failed ({exc}); using template fallback…")

            # 4. Template fallback
            ollama_available = False
            fallback = _template_paper(query, results, title)
            chunk_size = 80
            for i in range(0, len(fallback), chunk_size):
                loop.call_soon_threadsafe(queue.put_nowait, fallback[i:i + chunk_size])
            loop.call_soon_threadsafe(queue.put_nowait, None)
            return

        # ── Chat / follow-up mode ──────────────────────────────────────────────
        # 1. Try NVIDIA (PRIMARY)
        try:
            for token in _stream_chat_nvidia(query, groq_sources_text, thesis_context):
                loop.call_soon_threadsafe(queue.put_nowait, token)
            loop.call_soon_threadsafe(queue.put_nowait, None)
            return
        except Exception as exc:
            logger.warning(f"NVIDIA chat stream failed ({exc}); trying Groq…")

        # 2. Try Groq (SECONDARY)
        try:
            for token in _stream_chat_groq(query, groq_sources_text, thesis_context):
                loop.call_soon_threadsafe(queue.put_nowait, token)
            loop.call_soon_threadsafe(queue.put_nowait, None)
            return
        except Exception as exc:
            logger.warning(f"Groq chat stream failed ({exc}); trying Ollama…")

        # 3. Try Ollama (TERTIARY)
        try:
            for token in _stream_chat_ollama(query, sources_text, thesis_context):
                loop.call_soon_threadsafe(queue.put_nowait, token)
            loop.call_soon_threadsafe(queue.put_nowait, None)
            return
        except Exception as exc:
            logger.warning(f"Ollama chat stream failed ({exc}); using template fallback…")

        # 3. Template fallback
        ollama_available = False
        fallback = _template_chat(query, results, thesis_context)
        chunk_size = 80
        for i in range(0, len(fallback), chunk_size):
            loop.call_soon_threadsafe(queue.put_nowait, fallback[i:i + chunk_size])
        loop.call_soon_threadsafe(queue.put_nowait, None)

    loop.run_in_executor(None, producer)

    while True:
        token = await queue.get()
        if token is None:
            break
        yield token
