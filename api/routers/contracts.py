"""
Contract clause review — rule-based risk flags + statutes retrieved from the corpus.

This is a triage aid, not legal advice: flags are pattern matches on the pasted
text. No flag does NOT mean a clause is safe. Every result is pending_review.
"""
import re

from fastapi import APIRouter, Depends, HTTPException

from api.auth import verify_token
from api.deps import get_db
from api.rag import retriever as retriever_mod
from api.schemas import ContractRequest

router = APIRouter(prefix="/contracts", tags=["Contracts"], dependencies=[Depends(verify_token)])

SEVERITIES = ["Low", "Medium", "High"]

# focus area -> list of (regex, title, why it matters, base severity index)
RULES: dict[str, list[tuple[str, str, str, int]]] = {
    "Liability & Indemnity": [
        (r"indemnif|hold harmless", "Indemnity obligation present",
         "Check whether the indemnity is mutual, capped, and limited to third-party claims.", 2),
        (r"unlimited liability|uncapped|no (?:limit|cap) on liability", "Uncapped liability",
         "Liability appears unlimited; consider whether a cap tied to fees paid is expected.", 2),
        (r"consequential|indirect|incidental|loss of profit", "Damages exclusion wording",
         "Review which losses are excluded and whether the exclusion is mutual.", 1),
    ],
    "Intellectual Property": [
        (r"work(?:s)? made for hire|assigns? (?:all )?(?:right|title|interest)", "IP assignment",
         "Rights appear to transfer outright; confirm scope and whether background IP is carved out.", 2),
        (r"perpetual|irrevocable|royalty[- ]free", "Broad licence grant",
         "A perpetual/irrevocable licence is hard to unwind; confirm intent.", 1),
        (r"intellectual property|copyright|patent|trade ?mark", "IP terms present",
         "Check ownership of deliverables and pre-existing materials.", 0),
    ],
    "Termination & Renewal": [
        (r"auto(?:matic(?:ally)?)?[- ]renew|evergreen", "Automatic renewal",
         "Note the opt-out window; missed notice dates are a common trap.", 1),
        (r"terminate\w* for convenience|at any time without cause", "Termination for convenience",
         "Check who holds the right and what notice or fees apply.", 1),
        (r"\b(?:\d+|thirty|sixty|ninety)\s*(?:\(\d+\)\s*)?days'? (?:prior )?(?:written )?notice", "Notice period",
         "Confirm the notice period is workable for both sides.", 0),
    ],
    "Governing Law & Dispute": [
        (r"governed by|governing law", "Governing-law clause present",
         "Confirm the chosen law matches the jurisdiction you are reviewing under.", 0),
        (r"arbitrat", "Arbitration clause",
         "Check seat, rules, and whether court access is waived.", 1),
        (r"exclusive jurisdiction|submit to the (?:exclusive )?jurisdiction", "Exclusive forum",
         "Confirm the forum is convenient and enforceable.", 1),
    ],
}
MISSING = {
    "Liability & Indemnity": (r"liabilit", "No liability language found",
                              "The text has no limitation-of-liability wording; confirm it is covered elsewhere.", 1),
    "Governing Law & Dispute": (r"governed by|governing law|jurisdiction|arbitrat",
                                "No governing law or forum found",
                                "Add or locate governing-law and dispute-resolution terms.", 1),
}


MISSING_MIN_CHARS = 3000  # "no liability clause found" is only meaningful for a whole document


def _bump(idx: int, tolerance: str) -> int:
    if tolerance.startswith("Conservative"):
        idx += 1
    elif tolerance == "Aggressive":
        idx -= 1
    return max(0, min(idx, 2))


def analyze_clause(clause: str, focus_areas: list[str], tolerance: str) -> list[dict]:
    flags = []
    for area in focus_areas:
        for pattern, title, why, base in RULES.get(area, []):
            m = re.search(pattern, clause, re.I)
            if m:
                s = clause[max(0, m.start() - 60): m.end() + 80].replace("\n", " ").strip()
                flags.append({"focus": area, "title": title, "detail": why,
                              "severity": SEVERITIES[_bump(base, tolerance)], "excerpt": s})
        if area in MISSING and len(clause) >= MISSING_MIN_CHARS and not re.search(MISSING[area][0], clause, re.I):
            _, title, why, base = MISSING[area]
            flags.append({"focus": area, "title": title, "detail": why,
                          "severity": SEVERITIES[_bump(base, tolerance)], "excerpt": ""})
    return flags


@router.post("/analyze")
def analyze(body: ContractRequest, db=Depends(get_db)):
    unknown = [a for a in body.focus_areas if a not in RULES]
    if unknown:
        raise HTTPException(400, f"Unknown focus area(s): {unknown}. Valid: {list(RULES)}")

    flags = analyze_clause(body.clause, body.focus_areas, body.risk_tolerance)
    risk = max((SEVERITIES.index(f["severity"]) for f in flags), default=0)
    risk_level = SEVERITIES[risk]

    search_q = f"{body.agreement_type} {' '.join(body.focus_areas)} {body.clause[:400]}"
    try:
        provisions = retriever_mod.retrieve(search_q, body.jurisdiction)
    except Exception:
        provisions = []

    related = [{"id": p["id"], "statute_name": p.get("statute_name"), "section": p.get("section"),
                "excerpt": (p.get("content") or "")[:400], "rrf_rank": p.get("rrf_rank")} for p in provisions]

    summary = (
        f"Pattern-based review of a {body.agreement_type} clause under {body.jurisdiction} "
        f"jurisdiction raised {len(flags)} point(s) for attention (highest: {risk_level}). "
        "This is a triage aid only — absence of a flag does not mean a clause is safe."
    )
    saved = db.table("compliance_checks").insert({
        "check_type": "contract", "jurisdiction": body.jurisdiction,
        "query": body.clause[:2000], "citations": related,
        "raw_output": summary, "validated_output": None,
        "status": "pending_review", "agent_log": [{"action": "contract_rules", "flags": len(flags), "document": body.document_name}],
    }).execute()

    return {
        "risk_level": risk_level, "summary": summary, "flags": flags,
        "related_provisions": related, "review_status": "pending_review",
        "check_id": saved.data[0]["id"] if saved.data else None,
        "disclaimer": "Research aid only. Not legal advice. Requires review by a qualified lawyer.",
    }
