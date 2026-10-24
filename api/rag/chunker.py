"""
Statute chunker — 512-token chunks, 64-token overlap, measured with the bge tokenizer.
"""
import re
from typing import Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter

from api.rag import embedder  # referenced as embedder.tokenizer_len so tests can patch it

CHUNK_TOKENS = 512
OVERLAP_TOKENS = 64

# Legal-aware separators, tried largest first
LEGAL_SEPARATORS = [
    "\n\n\n",
    "\n\n",
    "\nSection ",
    "\nArticle ",
    "\nArt. ",
    "\n§ ",
    "\n(a) ",
    "\n(1) ",
    "\n",
    ". ",
    " ",
    "",
]

_SECTION_PATTERNS = [
    r"Section\s+\d+[A-Z]?",
    r"§\s*\d+(?:\.\d+)*[A-Za-z]?",
    r"Art(?:icle)?\.?\s*\d+",
    r"S\.\s*\d+[A-Z]?",
]


def get_chunker() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_TOKENS,
        chunk_overlap=OVERLAP_TOKENS,
        length_function=lambda t: embedder.tokenizer_len(t),
        separators=LEGAL_SEPARATORS,
    )


def _extract_section(chunk: str) -> str:
    """First section reference near the start of the chunk, or '' if none."""
    for p in _SECTION_PATTERNS:
        m = re.search(p, chunk[:300])
        if m:
            return m.group(0).strip()
    return ""


def chunk_text(
    text: str,
    statute_name: str,
    jurisdiction: str,
    year: Optional[int] = None,
    corpus_type: str = "statute",
    section: Optional[str] = None,
    fallback_section: Optional[str] = None,
) -> list[dict]:
    """
    Split text and attach metadata to every chunk.

    `section`: when the caller already knows the section (because it parsed the
    XML per-section), pass it and it is used verbatim for every chunk. Otherwise
    we guess from the chunk text, and if that finds nothing we use
    `fallback_section` (e.g. a CFR part title), then "chunk_<n>".

    Each chunk is prefixed with "<statute> — <section>" so the statute name is
    searchable by both the vector and the full-text legs of retrieval.
    """
    text = (text or "").strip()
    if not text:
        return []
    raw = get_chunker().split_text(text)
    chunks = []
    for i, body in enumerate(raw):
        sec = section or _extract_section(body) or fallback_section or ""
        content = f"{statute_name} — {sec}\n{body}" if sec else body
        chunks.append(
            {
                "content": content,
                "statute_name": statute_name,
                "jurisdiction": jurisdiction,
                "year": year,
                "corpus_type": corpus_type,
                "section": sec or f"chunk_{i}",
                "metadata": {
                    "chunk_index": i,
                    "total_chunks": len(raw),
                    "token_count": embedder.tokenizer_len(body),
                },
            }
        )
    return chunks
