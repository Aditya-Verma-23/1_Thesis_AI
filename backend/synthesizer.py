"""Synthesis engine: generates a structured thesis paper from top-10 sources.

Strategy:
  1. Try a local Ollama model (OpenAI-compatible endpoint).
  2. If Ollama is unreachable, fall back to a template-based assembler
     that still produces a coherent, properly formatted paper purely from
     the search snippets — no LLM needed.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import requests
from loguru import logger

from models import SearchResult

OLLAMA_URL   = "http://localhost:11434/v1/chat/completions"
OLLAMA_MODEL = "qwen2.5:14b-instruct"
TIMEOUT_S    = 120

async def suggest_alternative_topics(query: str) -> list[str]:
    """Generates 3 alternative but related research queries using the LLM."""
    prompt = (
        f"The user searched for a thesis topic '{query}' but found no results. "
        f"Suggest 3 alternative, more specific, or slightly broader thesis topics "
        f"they could research instead. Return ONLY the 3 suggestions, one per line, "
        f"with no intro, outtro, bullet points or numbering."
    )
    
    loop = asyncio.get_running_loop()
    def _call():
        return requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "temperature": 0.7,
            },
            timeout=10,
        )
    
    try:
        resp = await loop.run_in_executor(None, _call)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        suggestions = [line.strip().lstrip("-*1234567890. ") for line in content.split("\n") if line.strip()]
        return suggestions[:3] if suggestions else []
    except Exception as exc:
        logger.warning(f"Failed to generate alternative topics: {exc}")
        return []

SYSTEM_PROMPT = """\
You are ThesisAI, an expert academic writing assistant.

Given a research question and a numbered list of sources (each with their URL and full content), \
write a comprehensive, highly detailed academic thesis paper.

═══ STRICT FORMATTING RULES ═══

1.  The FIRST line must be a top-level Markdown heading with the paper title:
    # [A descriptive, specific title for the paper]

2.  Use ## for section headings (do NOT add numbers before section names):
    ## Abstract
    ## Introduction
    ## [Thematic section 1 — give it a specific, descriptive name]
    ## [Thematic section 2 — give it a specific, descriptive name]
    ## [Thematic section 3 — give it a specific, descriptive name if needed]
    ## Discussion
    ## Conclusion
    ## References

3.  CITATIONS: Every factual claim MUST be followed by an inline citation in brackets, e.g. [1] or [2].
    - Never write a paragraph without at least one citation.
    - Do not cluster all citations at the end of a paragraph; sprinkle them throughout.

4.  LENGTH: Write AT LEAST 1200 words of body text. Each section (except Abstract and Conclusion) \
must have at least 2–3 substantial paragraphs.

5.  REFERENCES section at the end — use this EXACT format for each entry on its OWN line:
    [[1]](URL) Title of the paper or page — URL
    [[2]](URL) Title of the paper or page — URL
    …
    The number [1], [2] etc. MUST be a clickable Markdown link pointing to the source URL.
    Each reference MUST be on a separate line with a blank line between entries.

6.  Do NOT use bullet points in the main sections — write in full, formal academic prose only.

7.  Do NOT invent facts or URLs not present in the sources provided.

═══ WRITING STYLE ═══
- Formal, academic English.
- Analyse each source deeply: discuss its methodology, findings, and implications.
- Connect ideas across sources — show synthesis, agreement, contradiction, and gaps.
- The thematic sections in the Literature Review should be named descriptively \
  (e.g. "Deep Learning Architectures for Disease Detection") not generically.\
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


# ── Title generation (quick non-streaming Ollama call) ────────────────────────

def _generate_title_sync(query: str) -> str:
    """Ask Ollama to produce a refined academic title. Falls back to a cleaned query."""
    try:
        payload = {
            "model":       OLLAMA_MODEL,
            "temperature": 0.4,
            "stream":      False,
            "messages": [
                {"role": "system", "content": TITLE_PROMPT},
                {"role": "user",   "content": query},
            ],
        }
        resp = requests.post(OLLAMA_URL, json=payload, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        title = data["choices"][0]["message"]["content"].strip().strip('"').strip()
        # Remove any leading `# ` that the model might add
        title = title.lstrip("# ").strip()
        logger.info(f"LLM-generated title: {title}")
        return title
    except Exception as exc:
        logger.warning(f"Title generation failed ({exc}); using fallback title logic")
        # Rule-based fallback: take first 10 words, title-case them
        words = query.split()
        short = " ".join(words[:10])
        return short.rstrip("?.!") + ("..." if len(words) > 10 else "")


# ── Ollama streaming helper (runs in a thread) ────────────────────────────────

def _stream_sync(query: str, sources_text: str, title: str):
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
    with requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT_S, stream=True) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
                delta = chunk["choices"][0]["delta"].get("content")
                if delta:
                    yield delta
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
        f"[[{r.index}]]({r.url}) {r.title}  \n&nbsp;&nbsp;&nbsp;&nbsp;{r.url}" for r in results
    )

    # Build a literature review paragraph per source
    lit_paragraphs = []
    for r in results:
        if not r.snippet and not getattr(r, "full_text", ""):
            continue
        content = getattr(r, "full_text", "") or r.snippet
        # Use first 400 chars of content for the paragraph seed
        excerpt = content[:400].strip().rstrip(".,;")
        if not excerpt:
            continue
        lit_paragraphs.append(
            f"{excerpt} {_cite(r.index)}. "
            f"This source ({r.title}) provides key insight into the topic by examining relevant "
            f"dimensions of *{query}*. The findings presented therein contribute substantively to "
            f"the understanding of this research area {_cite(r.index)}."
        )

    lit_text = "\n\n".join(lit_paragraphs) if lit_paragraphs else (
        f"The retrieved sources collectively address *{query}* from multiple angles. "
        f"Each of the {len(results)} sources contributes a distinct perspective, "
        f"collectively enriching the scholarly discourse on this topic."
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
            f"A cluster of the retrieved sources — including {titles} — "
            f"converges on key themes related to *{query}* {citations}. "
            f"These works share a common emphasis on empirical investigation and "
            f"provide robust evidence for the claims examined in this paper. "
            f"Notably, each source adopts a distinct methodological stance, offering "
            f"complementary perspectives that together form a cohesive body of evidence {citations}."
        )

    all_cites = " ".join(_cite(r.index) for r in results)

    paper = f"""# {title}

## Abstract

This paper presents a comprehensive synthesis of {len(results)} online academic sources addressing the research question: *"{query}"*. The sources span peer-reviewed journal articles, preprints, and academic web pages retrieved from leading scholarly databases. Through systematic analysis of the retrieved literature, this review identifies key themes, methodological approaches, and findings relevant to the query. The synthesis reveals a rich and active body of research, with sources collectively providing both empirical evidence and theoretical frameworks pertinent to the topic {_cite(results[0].index) if results else ""}.

## Introduction

The research question *"{query}"* occupies a significant position within contemporary academic discourse. As knowledge in this area continues to evolve rapidly, a systematic synthesis of available literature is essential to map the current state of evidence and identify pathways for future investigation. The present review draws on {len(results)} sources retrieved from authoritative academic repositories, including peer-reviewed articles and preprint servers. Each source has been selected on the basis of topical relevance, and together they provide a multifaceted view of the subject matter {all_cites}.

The importance of understanding *"{query}"* cannot be overstated. Scholars and practitioners alike have recognised the need for rigorous, evidence-based frameworks that can guide both theoretical understanding and applied decision-making. This synthesis aims to distil the essential insights from the available literature, presenting them in a coherent structure that facilitates both comprehension and further inquiry.

## Thematic Analysis of the Literature

{group_summary(group_a)}

{group_summary(group_b)}

The literature collectively demonstrates that *"{query}"* is approached from multiple disciplinary angles. Researchers have employed a variety of methodologies — ranging from experimental designs and computational modelling to meta-analyses and systematic reviews — each yielding complementary insights {all_cites}. The diversity of approaches reflects the interdisciplinary nature of the topic and underscores the value of cross-disciplinary synthesis.

## Detailed Review of Sources

{lit_text}

Across the reviewed sources, a number of recurring themes emerge. First, there is broad consensus that *"{query}"* represents a domain of active and growing scholarly interest, with publication rates increasing steadily in recent years {_cite(results[-1].index) if results else ""}. Second, methodological heterogeneity characterises the field: quantitative, qualitative, and mixed-methods studies all feature prominently. This diversity, while challenging for synthesis, enriches the overall evidence base and allows for triangulation of findings. Third, several sources highlight critical gaps in the existing literature, pointing to areas where further empirical work is urgently needed {all_cites}.

## Discussion

The synthesis of the {len(results)} retrieved sources yields several important insights regarding *"{query}"*. Taken together, the sources paint a picture of a field that is both well-established in its foundational concepts and dynamically evolving in its applied dimensions {all_cites}. Key debates within the literature centre on methodological best practices, the generalisability of findings across contexts, and the most productive directions for future inquiry.

It is notable that, despite the breadth of the literature, certain questions remain underexplored. Future research should seek to address these gaps by employing longitudinal designs, larger and more diverse samples, and interdisciplinary collaborations. The findings reviewed here suggest that progress in understanding *"{query}"* will depend critically on the continued integration of insights from adjacent fields and on the development of more robust theoretical frameworks {all_cites}.

## Conclusion

This review has synthesised current scholarly evidence on *"{query}"*, drawing on {len(results)} peer-reviewed and academic sources. The analysis reveals a dynamic and growing field, characterised by methodological diversity and a wealth of empirical evidence. While significant progress has been made, important gaps remain, and the field would benefit from more integrative, longitudinal research designs. The sources reviewed here collectively provide a strong foundation for future inquiry and offer valuable guidance for both researchers and practitioners engaged with this topic {all_cites}.

## References

{refs_section}

---
*Generated by Thesis AI*
"""
    return paper


# ── Public async streaming synthesizer ───────────────────────────────────────

def _format_sources(results: list[SearchResult]) -> str:
    lines = []
    for r in results:
        content = getattr(r, "full_text", "")
        if not content or len(content.strip()) < 50:
            content = r.snippet
        lines.append(
            f"[{r.index}] {r.title}\n"
            f"URL: {r.url}\n"
            f"Content:\n{content}\n"
        )
    return "\n\n---\n\n".join(lines) if lines else "(no sources)"


async def synthesize(query: str, results: list[SearchResult]) -> AsyncIterator[str]:
    """Yield paper tokens. Falls back to template if Ollama is offline."""
    sources_text = _format_sources(results)

    queue: asyncio.Queue[str | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()
    ollama_available = True

    def producer():
        nonlocal ollama_available
        # Step 1: generate a refined title via LLM (quick, non-streaming)
        title = _generate_title_sync(query)
        logger.info(f"Using title: {title}")
        try:
            for token in _stream_sync(query, sources_text, title):
                loop.call_soon_threadsafe(queue.put_nowait, token)
        except Exception as exc:
            err_msg = f"Ollama unavailable ({exc}); using template fallback"
            logger.warning(err_msg)
            ollama_available = False
            
            # Generate template and inject a visible warning at the very top
            fallback = _template_paper(query, results, title)
            warning_md = f"> [!WARNING]\n> **{err_msg}**\n\n"
            fallback = warning_md + fallback
            
            chunk_size = 80
            for i in range(0, len(fallback), chunk_size):
                loop.call_soon_threadsafe(queue.put_nowait, fallback[i:i + chunk_size])
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    loop.run_in_executor(None, producer)

    while True:
        token = await queue.get()
        if token is None:
            break
        yield token
