"""
Jurisdiction router — a SUGGESTION, never an authority.
The jurisdiction the user picks in the UI always wins; a silently mis-routed
jurisdiction is a serious error in legal work.

Stage 1: word-boundary regex (acronyms are case-sensitive, names are not).
Stage 2: embedding similarity fallback.
"""
import re

import numpy as np

from api.rag import embedder

# (pattern, case_insensitive). Lookarounds instead of \b so "U.S." works.
_I, _S = True, False
PATTERNS: dict[str, list[tuple[str, bool]]] = {
    "US": [
        (r"(?<!\w)(United States|U\.S\.A?\.?|federal law|Congress|Senate)(?!\w)", _I),
        (r"\b(CFR|U\.S\.C\.|Federal Register|SCOTUS|IRS|SEC|FTC|FDA|HIPAA|CCPA)\b", _S),
        (r"\b(California|New York|Texas|Delaware|Florida|Illinois)\b", _I),
        (r"\bSection 230\b", _I),
    ],
    "CA": [
        (r"\b(Canada|Canadian)\b", _I),
        (r"\b(Ontario|Quebec|Alberta|British Columbia|Manitoba)\b", _I),
        (r"\b(CRA|CBCA|PIPEDA|Competition Act|Employment Insurance)\b", _S),
        (r"\b(Supreme Court of Canada|Federal Court of Canada|SCC)\b", _S),
    ],
    "UK": [
        (r"\b(United Kingdom|England|Wales|Scotland|Northern Ireland)\b", _I),
        (r"\bUK\b", _S),
        (r"\b(Companies House|HMRC|ICO|FCA|CMA)\b", _S),
        (r"\b(Companies Act 2006|UK GDPR|Employment Rights Act)\b", _I),
    ],
    "EU": [
        (r"\b(European Union|European Commission)\b", _I),
        (r"\bEU\b", _S),
        (r"\b(GDPR|AI Act|Digital Markets Act|Digital Services Act)\b", _I),
        (r"\b(CJEU|Court of Justice|Advocate General)\b", _I),
        (r"\bCELEX\b", _S),
    ],
}

ANCHORS = {
    "US": "United States federal law US Code CFR Congress SCOTUS IRS SEC",
    "CA": "Canada Canadian law CBCA PIPEDA CRA Competition Act Ontario Quebec",
    "UK": "United Kingdom UK law Companies Act 2006 HMRC ICO Employment Rights",
    "EU": "European Union EU law GDPR AI Act CJEU Directive Regulation CELEX",
}

SEMANTIC_THRESHOLD = 0.45
_anchor_cache: dict | None = None


def _anchors() -> dict:
    global _anchor_cache
    if _anchor_cache is None:
        _anchor_cache = {j: embedder.embed_query(t) for j, t in ANCHORS.items()}
    return _anchor_cache


def classify(text: str) -> dict:
    scores = {}
    for jx, pats in PATTERNS.items():
        scores[jx] = sum(
            1 for p, ci in pats if re.search(p, text, re.I if ci else 0)
        )

    best = max(scores, key=scores.get)
    if scores[best] > 0:
        top_two = sorted(scores.values(), reverse=True)[:2]
        tie = top_two[0] == top_two[1]
        return {
            "suggestion": "AMBIGUOUS" if tie else best,
            "confidence": min(scores[best] / 3.0, 1.0),
            "method": "regex",
            "scores": scores,
            "tie": tie,
        }

    try:
        qvec = embedder.embed_query(text)
        sims = {j: float(np.dot(qvec, av)) for j, av in _anchors().items()}
    except Exception:  # embedding model unavailable → degrade gracefully
        return {"suggestion": "UNKNOWN", "confidence": 0.0, "method": "none"}
    best = max(sims, key=sims.get)
    if sims[best] < SEMANTIC_THRESHOLD:
        return {"suggestion": "UNKNOWN", "confidence": sims[best], "method": "semantic"}
    return {"suggestion": best, "confidence": sims[best], "method": "semantic"}
