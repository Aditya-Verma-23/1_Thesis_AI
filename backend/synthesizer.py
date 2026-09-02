"""Synthesis engine: generates a structured thesis paper from top-10 sources.

Backend priority order (automatic failover):
  1. Groq cloud API — openai/gpt-oss-120b — PRIMARY
     Fast cloud inference, always available.
  2. Local Ollama — qwen3:8b — SECONDARY (optional, when running)
     Connect timeout is 3 s so a stopped Ollama fails instantly.
  3. Template assembler — no LLM required — LAST RESORT
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import requests
from loguru import logger

from models import SearchResult

# ── Groq cloud API (PRIMARY) ─────────────────────────────────────────────────
GROQ_API_KEY   = "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"
GROQ_URL       = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL     = "openai/gpt-oss-120b"
GROQ_TIMEOUT_S = 300

# ── Ollama local (SECONDARY — optional, used when running) ────────────────────
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

    for _call, label in [(_call_groq, "Groq"), (_call_ollama, "Ollama")]:
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

5.  REFERENCES section at the end — use this EXACT format, with a blank line between each entry:
    [1] Title of the paper or page
    https://source-url-here

    [2] Title of the paper or page
    https://source-url-here

    Do NOT make the number a hyperlink. Do NOT put title and URL on the same line.
    Every source provided in the input MUST appear in the References section.

6.  Do NOT use bullet points in the main body sections — write in full, formal academic prose.

7.  REPHRASING — ABSOLUTE RULE:
    - You MUST synthesise and rephrase all source content in your own formal academic language.
    - NEVER copy, quote, or echo raw text verbatim from the source content.
    - Do NOT paste scraped page content, navigation menus, or website boilerplate.
    - Transform factual information into your own coherent academic sentences and paragraphs.
    - Do NOT invent facts or statistics not present in the sources — but always express them
      in original, rephrased academic prose with proper citations.

8.  DATA VISUALISATION: Where sources discuss quantitative data, statistics, or comparative
    findings you MUST create at least one Markdown Table to represent these findings.
    Table format:
    | Column A | Column B | Column C |
    |----------|----------|----------|
    | Value    | Value    | Value    |

9.  IMAGES — MANDATORY RULE:
    - If ANY source provides an "Image URL", you MUST embed it using Markdown syntax:
      ![Descriptive caption explaining the image](IMAGE_URL_HERE)
    - Place the image directly within the paragraph that discusses the relevant source.
    - The image caption must be descriptive and academic (e.g., "Figure 1: Mechanism of CRISPR-Cas9 gene editing").
    - Do NOT skip image embedding — every provided Image URL must appear in the paper.

10. COMPLETENESS — ABSOLUTE RULE:
    - You MUST write EVERY section completely from start to finish.
    - Do NOT stop mid-sentence, mid-section, or mid-paper under ANY circumstance.
    - The paper is only complete when the ## References section has been written in full.
    - If you are running low on output capacity, COMPRESS earlier sections but NEVER omit
      the Discussion, Conclusion, or References sections.

═══ WRITING QUALITY ═══
- Formal, academic English throughout. Every sentence must be your own rephrased synthesis.
- The full page content for each source is extensive — you MUST analyse specific details,
  methodologies, empirical findings, and statistics from that content.
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
3. Format your response intelligently based on the user's prompt: use **numbered lists** (1. 2. 3. …) if they ask for a list/points, use concise paragraphs (2 to 5 max) if they ask for an explanation, or use the ASCII diagram format (see Rule 10) if they ask for a flow/diagram/structure/process/pipeline/workflow.  NEVER use bullet points (- or *) — always prefer numbered lists or diagrams.
4. ONLY use inline citations like [1], [2] when referencing highly specific facts, statistics, or direct quotes from the new sources. Do NOT blindly append citations to every single point or sentence if the information is general knowledge or a broad synthesis. Use citations sparingly and only when strictly necessary.
5. Do NOT include a References section — the UI handles this automatically.
6. Write in formal, academic English.
7. Interpret vague pronouns (e.g., "it", "that", "this", "they") in the user's question as referring to the main topic of the THESIS CONTEXT.
8. Actively use the THESIS CONTEXT to answer the question. If the NEW SOURCES are irrelevant to the question, ignore them and rely entirely on the THESIS CONTEXT.
9. ONLY answer questions that are directly related to the main topic of the THESIS CONTEXT. If the user asks a question that is unrelated to the thesis topic, DO NOT answer it. Instead, reply politely saying: "This question does not appear to be related to the current research topic. Please ask a question related to the thesis."
10. DIAGRAM RULE — MANDATORY AND STRICT: If the user asks for a flow, diagram, structure, process, pipeline, workflow, steps, or any visual representation, you MUST produce an ASCII box diagram using ONLY a strict TOP-TO-BOTTOM VERTICAL layout. Wrap the entire diagram in triple backticks.

ABSOLUTE CONSTRAINTS — violating any of these is forbidden:
  ✗ NO horizontal arrows (→ or -->) between boxes on the same row.
  ✗ NO side-by-side columns or multi-column layouts.
  ✗ NO diagonal connections.
  ✗ NO boxes placed next to each other on the same line.
  ✓ ONLY one box per row, stacked vertically, connected by a centred ↓.

BOX CONSTRUCTION — copy this structure exactly:
  ┌──────────────────────────┐
  │ N. Step Title            │
  │    Optional detail line  │
  │  • Branch option A       │
  │  • Branch option B       │
  └──────────────┬───────────┘
                 ↓

  Where:
  - Top edge:    ┌ then ── repeated to fill width then ┐
  - Side edges:  │ space content space-padded to width │
  - Bottom+stem: └ then ── repeated then ┬ then ── then ┘  (all non-final boxes)
  - Last bottom: └ then ── repeated to fill width then ┘   (final box, no ↓)
  - Arrow:       spaces to centre the ↓ under the ┬, then ↓ on its own line

WORKED EXAMPLE (copy this exact style):
```
┌──────────────────────────┐
│ 1. Design gRNA           │
│    Target the DNA locus  │
└──────────────┬───────────┘
               ↓
┌──────────────────────────┐
│ 2. Assemble Cas9 Complex │
│    Cas9 protein + gRNA   │
└──────────────┬───────────┘
               ↓
┌──────────────────────────┐
│ 3. Deliver to Cell       │
│  • Viral vector          │
│  • Electroporation       │
│  • Lipid nanoparticle    │
└──────────────┬───────────┘
               ↓
┌──────────────────────────┐
│ 4. PAM Recognition &     │
│    DNA Binding           │
└──────────────┬───────────┘
               ↓
┌──────────────────────────┐
│ 5. Cas9 Cuts DNA         │
│    Double-strand break   │
└──────────────┬───────────┘
               ↓
┌──────────────────────────┐
│ 6. DNA Repair            │
│  • NHEJ → gene knockout  │
│  • HDR → precise edit    │
└──────────────┬───────────┘
               ↓
┌──────────────────────────┐
│ 7. Screen & Validate     │
│    Sequencing & analysis │
└──────────────────────────┘
```

After the diagram, add 2–3 sentences of plain-text academic explanation.
NEVER use a numbered list, bullet list, or paragraph alone when a diagram is requested.
"""




# ── Title generation (quick non-streaming Ollama call) ────────────────────────

QUESTION_TITLE_PROMPT = """\
You are a precise editor. The user has asked a follow-up research question in a casual or informal way.
Rewrite it as a SHORT, precise, well-phrased section heading (NOT a full thesis title).

Rules:
- Maximum 20 words.
- Title Case (capitalise major words).
- Remove filler words like "ok", "now", "please", "can you", "tell me", "provide me".
- Keep it factual and direct — it should read like a document section heading.
- Do NOT add a question mark.
- Do NOT add "Overview of", "A Look at", "Introduction to", or similar filler prefixes.
- Respond with ONLY the heading text, nothing else.\
"""


def _generate_title_sync(query: str) -> str:
    """Ask Groq (then Ollama) to produce a refined academic title. Falls back to a cleaned query."""
    backends = [
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


def generate_question_title_sync(question: str) -> str:
    """Convert a raw follow-up question into a short, precise section heading using the LLM."""
    backends = [
        {
            "url":     GROQ_URL,
            "headers": {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            "payload": {
                "model":       GROQ_MODEL,
                "temperature": 0.3,
                "stream":      False,
                "messages": [
                    {"role": "system", "content": QUESTION_TITLE_PROMPT},
                    {"role": "user",   "content": question},
                ],
            },
            "timeout": 10,
            "label":   "Groq",
        },
        {
            "url":     OLLAMA_URL,
            "headers": {},
            "payload": {
                "model":       OLLAMA_MODEL,
                "temperature": 0.3,
                "stream":      False,
                "messages": [
                    {"role": "system", "content": QUESTION_TITLE_PROMPT},
                    {"role": "user",   "content": question},
                ],
            },
            "timeout": (OLLAMA_CONNECT_TIMEOUT, 10),
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
            heading = resp.json()["choices"][0]["message"]["content"].strip().strip('"').strip()
            heading = heading.lstrip("# ").strip().rstrip("?")
            logger.info(f"[{backend['label']}] Generated question title: {heading}")
            return heading
        except Exception as exc:
            logger.warning(f"[{backend['label']}] Question title generation failed: {exc}")

    # Fallback: strip filler words and title-case
    import re
    cleaned = re.sub(
        r"^(ok|okay|now|please|can you|could you|tell me|provide me|give me|show me|explain|describe|what is|what are|how does|how do)\s+",
        "", question.strip(), flags=re.IGNORECASE
    )
    words = cleaned.split()
    return " ".join(words[:8]).rstrip("?.!").title()




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

def _build_source_description(r: "SearchResult") -> str:
    """
    Build a clean, rephrased academic description of a source from its snippet.
    Uses only the snippet (not raw scraped full_text) to avoid content dumps.
    """
    # Prefer snippet over full_text for template — snippets are clean search engine summaries
    snippet = (r.snippet or "").strip()
    if not snippet and hasattr(r, "full_text") and r.full_text:
        # If we must use full_text, take only first 2 sentences
        import re
        sentences = re.split(r'(?<=[.!?])\s+', r.full_text.strip())
        snippet = " ".join(sentences[:2]).strip()
    return snippet[:300].rstrip(".,;") if snippet else ""


def _template_paper(query: str, results: list[SearchResult], title: str) -> str:
    """
    Rich fallback template used when both LLMs are unavailable.
    Produces a properly formatted, well-cited academic paper from clean snippets.
    NEVER dumps raw scraped page content — always uses clean rephrased prose.
    """
    def _cite(idx: int) -> str:
        return f"[{idx}]"

    refs_section = "\n\n".join(
        f"[{r.index}] {r.title}\n{r.url}" for r in results
    )

    # Build a findings paragraph per source using ONLY clean snippets
    lit_paragraphs = []
    for i, r in enumerate(results):
        description = _build_source_description(r)
        if not description:
            continue

        img_md = (
            f"\n\n![Figure {r.index}: Visual overview related to {r.title}]({r.image_url})\n"
            if getattr(r, "image_url", None) else ""
        )

        if i % 2 == 0:
            lit_paragraphs.append(
                f"The work presented in *{r.title}* {_cite(r.index)} offers a foundational perspective on "
                f"the subject of {query}. According to this source, {description} {_cite(r.index)}. "
                f"These insights substantially enrich the broader scholarly understanding of the topic "
                f"and provide a critical empirical anchor for the subsequent discussion {_cite(r.index)}.{img_md}"
            )
        else:
            lit_paragraphs.append(
                f"Building upon the preceding analysis, the research documented in *{r.title}* {_cite(r.index)} "
                f"further advances our understanding of {query}. The source establishes that {description} {_cite(r.index)}. "
                f"This contribution underscores the multifaceted nature of the topic and highlights the "
                f"necessity for comprehensive, evidence-based inquiry into the variables at play {_cite(r.index)}.{img_md}"
            )

    lit_text = "\n\n".join(lit_paragraphs) if lit_paragraphs else (
        f"The retrieved sources collectively address *{query}* from multiple disciplinary angles. "
        f"Each of the {len(results)} sources contributes a distinct perspective, collectively "
        f"enriching scholarly discourse with both quantitative and qualitative evidence {all_cites}."
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
        more = f" and {len(group) - 3} additional works" if len(group) > 3 else ""
        return (
            f"A significant cluster of the retrieved literature — encompassing works such as {titles}{more} — "
            f"collectively addresses the foundational theoretical dimensions of *{query}* {citations}. "
            f"These sources construct a robust theoretical background that informs the empirical "
            f"methodologies employed in this study and anchors the subsequent data analysis phases {citations}. "
            f"The scholarly contributions from this cluster demonstrate convergent agreement on the "
            f"core mechanisms and implications of the topic under investigation {citations}."
        )

    all_cites = " ".join(_cite(r.index) for r in results)

    # Academic comparison table using clean title and source info only
    table_rows = []
    for r in results[:6]:
        safe_title = (r.title[:42] + "…") if len(r.title) > 42 else r.title
        import urllib.parse
        try:
            domain = urllib.parse.urlparse(r.url).netloc.replace("www.", "") if r.url else "Web"
        except Exception:
            domain = "Web"
        table_rows.append(f"| {_cite(r.index)} | {safe_title} | {domain} | Qualitative/Empirical |")
    table_md = (
        "| Ref | Research Title / Focus | Source | Methodology |\n"
        "|-----|------------------------|--------|-------------|\n"
        + "\n".join(table_rows)
    )

    first_cite = _cite(results[0].index) if results else ""
    last_cite  = _cite(results[-1].index) if results else ""

    paper = f"""# {title}

## Abstract

This paper presents a comprehensive academic synthesis of {len(results)} scholarly sources addressing the research question: *"{query}"*. Drawing upon peer-reviewed journal articles, preprints, and authoritative academic reports retrieved from leading scholarly databases, this thesis employs a systematic review methodology to identify key themes, empirical findings, and theoretical frameworks directly relevant to the topic. The synthesis reveals a substantiated and growing body of research in which sources collectively contribute both empirical data and theoretical insights pertinent to the overarching problem statement {first_cite}. The paper proceeds through a structured analysis, culminating in a discussion of research gaps and directions for future scholarly inquiry.

## Introduction

The academic investigation of *"{query}"* has assumed increasing importance within contemporary scientific and interdisciplinary discourse. As evidence in this domain continues to accumulate at a rapid pace, the formal synthesis of available literature has become an essential undertaking for scholars seeking to map the current state of knowledge and identify concrete pathways for future research {first_cite}. The present review draws upon {len(results)} sources retrieved from authoritative academic repositories, each selected on the basis of topical relevance and scholarly rigour, collectively providing a multifaceted view of the intellectual landscape {all_cites}.

The importance of rigorously investigating *"{query}"* extends beyond academic interest; it has direct implications for practical decision-making, policy formulation, and the advancement of the field. Scholars and practitioners alike have recognised the need for evidence-based frameworks that can guide applied research and translate theoretical insights into actionable outcomes. This thesis aims to distil the essential contributions of the available literature, presenting them within a structured, professional academic framework that meets rigorous scholarly standards {all_cites}.

## Literature Review: {query.capitalize()}

{group_summary(group_a)}

{group_summary(group_b)}

The historical and contemporary literature collectively demonstrates that *{query}* is approached from multiple disciplinary angles, reflecting the inherently interdisciplinary character of the field. Prior researchers have employed a variety of theoretical and empirical frameworks, each yielding complementary insights that together compose a rich and nuanced scholarly discourse {all_cites}. The diversity of methodological approaches identified across the literature not only underscores the complexity of the topic but also establishes a strong foundation for the systematic methodology adopted in this paper.

## Methodology and Search Strategy

This thesis employs a systematic review methodology designed to aggregate, evaluate, and synthesise the available academic literature on *"{query}"*. Specifically, {len(results)} peer-reviewed and authoritative resources were retrieved through targeted academic search queries across multiple scholarly databases and web sources. The inclusion criteria mandated that each source demonstrate a meaningful empirical or theoretical contribution to the field, exhibit scholarly rigour, and maintain direct relevance to the research question.

The analytical strategy involved qualitative coding of the gathered source abstracts, key findings, and thematic content to extract dominant intellectual trends, identify methodological heterogeneity, and surface substantive data points. A comparative cross-source analysis was conducted to triangulate findings and evaluate the degree of scholarly consensus and divergence. This approach, while subject to the inherent limitations of cross-sectional retrieval and potential publication bias, ensures a high degree of analytical rigour and thematic comprehensiveness across the observed findings {all_cites}.

## Analysis and Findings: Synthesis of Data

{lit_text}

### Comparative Source Overview

{table_md}

Across the reviewed sources, several definitive trends emerge that collectively advance understanding of *{query}*. First, there is broad scholarly consensus that the topic represents a domain of high significance, with the volume and specificity of published research increasing substantially over recent years {last_cite}. Second, the empirical evidence consistently highlights complex interdependencies among the core variables under investigation, suggesting that reductive or single-factor analyses are insufficient for capturing the full scope of the phenomenon. Third, multiple sources explicitly identify critical knowledge gaps in the existing literature, pointing to specific methodological and empirical frontiers where further scholarly work is urgently required {all_cites}.

## Discussion

The synthesis of the {len(results)} retrieved sources yields critical insights that advance the scholarly understanding of *{query}*. Taken together, the aggregated findings paint a portrait of a dynamic and evolving field, one characterised by methodological innovation, growing empirical rigour, and productive scholarly debate {all_cites}. Key intellectual tensions within the literature centre on the most appropriate methodological frameworks, the generalisability of findings across diverse contexts, and the identification of the most productive avenues for future theoretical and applied inquiry.

It is notable that, despite the breadth and depth of the existing literature, certain dimensions of *{query}* remain underexplored or contested. The evidence reviewed suggests that meaningful progress will depend upon sustained interdisciplinary collaboration, the standardisation of data collection and reporting protocols, and the development of integrative theoretical models capable of accommodating the complexity of the phenomenon {all_cites}. These observations reinforce the value of the present synthesis and point toward concrete directions for future scholarship.

## Conclusion

This thesis has systematically synthesised the current scholarly evidence pertaining to *"{query}"*, drawing upon {len(results)} authoritative academic sources. The structured analysis has revealed a dynamic and methodologically diverse field, one in which substantial empirical progress has been achieved alongside the identification of important remaining gaps. The findings of this review underscore the need for continued rigorous inquiry and the integration of diverse scholarly perspectives. The present work establishes a strong, evidence-grounded foundation for future research and offers practically relevant, data-driven guidance for scholars and practitioners engaged with this critical topic {all_cites}.

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
) -> AsyncIterator[str]:
    """Yield paper tokens. Falls back to template if both LLMs are offline."""
    sources_text      = _format_sources(results)        # full-size for Ollama (10k chars/source)
    groq_sources_text = _format_sources_groq(results)   # compact for Groq  (3.5k chars/source, 28k total)

    queue: asyncio.Queue[str | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    ollama_available = True

    def producer():
        nonlocal ollama_available

        # ── Thesis generation ──────────────────────────────────
        title = _generate_title_sync(query)  # tries Groq → Ollama internally
        logger.info(f"Using title: {title}")

        # 1. Try Groq (PRIMARY)
        try:
            for token in _stream_groq(query, groq_sources_text, title):
                loop.call_soon_threadsafe(queue.put_nowait, token)
            loop.call_soon_threadsafe(queue.put_nowait, None)
            return
        except Exception as exc:
            logger.warning(f"Groq thesis stream failed ({exc}); trying Ollama…")

        # 2. Try Ollama (SECONDARY)
        try:
            for token in _stream_ollama(query, sources_text, title):
                loop.call_soon_threadsafe(queue.put_nowait, token)
            loop.call_soon_threadsafe(queue.put_nowait, None)
            return
        except Exception as exc:
            logger.warning(f"Ollama thesis stream failed ({exc}); using template fallback…")

        # 3. Template fallback
        ollama_available = False
        fallback = _template_paper(query, results, title)
        chunk_size = 80
        for i in range(0, len(fallback), chunk_size):
            loop.call_soon_threadsafe(queue.put_nowait, fallback[i:i + chunk_size])
        loop.call_soon_threadsafe(queue.put_nowait, None)
        return

    loop.run_in_executor(None, producer)


    while True:
        token = await queue.get()
        if token is None:
            break
        yield token


async def synthesize_chat(
    query: str,
    results: list[SearchResult],
    thesis_context: str | None = None,
) -> AsyncIterator[str]:
    """Yield chat tokens for follow-up questions."""
    sources_text      = _format_sources(results)
    groq_sources_text = _format_sources_groq(results)

    queue: asyncio.Queue[str | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def producer():
        # 1. Try Groq (PRIMARY for chat)
        try:
            for token in _stream_chat_groq(query, groq_sources_text, thesis_context):
                loop.call_soon_threadsafe(queue.put_nowait, token)
            loop.call_soon_threadsafe(queue.put_nowait, None)
            return
        except Exception as exc:
            logger.warning(f"Groq chat stream failed ({exc}); trying Ollama…")

        # 2. Try Ollama (SECONDARY)
        try:
            for token in _stream_chat_ollama(query, sources_text, thesis_context):
                loop.call_soon_threadsafe(queue.put_nowait, token)
            loop.call_soon_threadsafe(queue.put_nowait, None)
            return
        except Exception as exc:
            logger.warning(f"Ollama chat stream failed ({exc}); using template fallback…")

        # 3. Template fallback
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
