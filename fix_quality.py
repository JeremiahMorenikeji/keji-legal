# fix_quality.py - answer-quality fixes found by the test queries. Safe to run twice.
# Nothing is written unless every required change can be applied.
from pathlib import Path
import sys

for must in ("api/agents/compliance_agent.py", "api/routers/contracts.py", "app/pages/03_contracts.py",
             "app/pages/02_compliance.py"):
    if not Path(must).exists():
        sys.exit("Run this from inside the keji-legal folder.")

changes, problems, done, skipped = {}, [], [], []


def cur(rel):
    return changes[rel] if rel in changes else Path(rel).read_text(encoding="utf-8")


def edit(rel, pairs, marker, optional=False):
    if not Path(rel).exists():
        (skipped if optional else problems).append(f"{rel}: file not found")
        return
    s = cur(rel)
    if marker in s:
        done.append(f"{rel} ({marker})")
        return
    for old, new in pairs:
        if old not in s:
            msg = f"{rel}: could not find: {old.strip().splitlines()[0][:70]}"
            (skipped if optional else problems).append(msg)
            return
        s = s.replace(old, new, 1)
    changes[rel] = s


# 1. The "procedural note" paraphrased the law and could not be checked (it once cited "52.01(6)", which was
#    never retrieved). Quotes are checked word-for-word; paraphrase is not, so the note is removed.
edit("api/agents/compliance_agent.py", [
    ("YOUR ONLY JOB: Cite the provisions above. Nothing else.\n",
     "YOUR ONLY JOB: Quote and cite the provisions above. Nothing else - no summaries, no procedure notes,\n"
     "no commentary of your own.\n"),
    ("PROCEDURAL NOTE:\n(Optional \u2014 one sentence on what procedure applies, citing the section)\n\n", ""),
], "no commentary of your own")

# 2. Contract review: "missing clause" flags only make sense for a WHOLE contract, not a one-clause paste.
edit("api/routers/contracts.py", [
    ("def _bump(idx: int, tolerance: str) -> int:",
     "MISSING_MIN_CHARS = 3000  # \"no liability clause found\" is only meaningful for a whole document\n\n\n"
     "def _bump(idx: int, tolerance: str) -> int:"),
    ("        if area in MISSING and not re.search(MISSING[area][0], clause, re.I):",
     "        if area in MISSING and len(clause) >= MISSING_MIN_CHARS and not re.search(MISSING[area][0], clause, re.I):"),
], "MISSING_MIN_CHARS")

# 3. Contract page: check ALL four risk areas by default; say that related statutes may be loose matches.
edit("app/pages/03_contracts.py", [
    ('focus = st.multiselect("Primary risk focus", FOCUS, default=["Liability & Indemnity"])',
     'focus = st.multiselect("Primary risk focus", FOCUS, default=FOCUS)'),
    ('st.markdown("### Related provisions in the corpus")',
     'st.markdown("### Closest statutes in the corpus (matches can be loose - check they are relevant)")'),
], "default=FOCUS)")

# 4. Compliance page: say which edition US regulations come from (they go out of date, e.g. annual fees).
edit("app/pages/02_compliance.py", [
    ('            st.markdown(f"**{len(cites)} provision(s) retrieved**")\n',
     '            st.markdown(f"**{len(cites)} provision(s) retrieved**")\n'
     '            _us = sorted({c.get("year") for c in cites if c.get("jurisdiction") == "US" and c.get("year")})\n'
     '            if _us:\n'
     '                st.caption(f"US regulations come from the {_us[-1]} CFR edition. Check the current eCFR for "\n'
     '                           "recent changes (for example annual fee amounts).")\n'),
], "CFR edition", optional=False)

# 5. Update the tests that described the old behaviour (skipped with a note if your test files differ).
edit("tests/test_api.py", [
    ('def test_contract_missing_governing_law_flagged(client):\n'
     '    r = client.post("/contracts/analyze", json={"clause": "The parties agree to cooperate in good faith always.",\n'
     '                                                "jurisdiction": "UK", "focus_areas": ["Governing Law & Dispute"]}).json()\n'
     '    assert any("No governing law" in f["title"] for f in r["flags"])\n',
     'def test_contract_missing_governing_law_flagged_only_for_whole_documents(client):\n'
     '    short = {"clause": "The parties agree to cooperate in good faith always.", "jurisdiction": "UK",\n'
     '             "focus_areas": ["Governing Law & Dispute"]}\n'
     '    assert not any("No governing law" in f["title"] for f in client.post("/contracts/analyze", json=short).json()["flags"])\n'
     '    whole = {**short, "clause": "The parties agree to cooperate in good faith always. " * 80}      # a whole document\n'
     '    assert any("No governing law" in f["title"] for f in client.post("/contracts/analyze", json=whole).json()["flags"])\n'),
], "only_for_whole_documents", optional=True)

edit("tests/test_frontend.py", [
    ('assert body["focus_areas"] == ["Liability & Indemnity"] and body["risk_tolerance"] == "Standard"',
     'assert len(body["focus_areas"]) == 4 and body["risk_tolerance"] == "Standard"      # all four areas by default'),
], "all four areas by default", optional=True)

if problems:
    print("Nothing was changed, because:")
    for p in problems:
        print("  !!", p)
    print("Send me these lines.")
    sys.exit(1)

for rel, text in changes.items():
    Path(rel + ".bak9").write_text(Path(rel).read_text(encoding="utf-8"), encoding="utf-8")
    Path(rel).write_text(text, encoding="utf-8")
    print(f"  patched: {rel}")
for rel in done:
    print(f"  already up to date: {rel}")
for s in skipped:
    print(f"  (skipped, optional) {s}")

TEST = '''"""Answer-quality guards found by running real test queries."""
from api.agents import compliance_agent


def test_prompt_no_longer_asks_for_an_unverifiable_procedural_note():
    assert "PROCEDURAL NOTE" not in compliance_agent.SYSTEM_PROMPT
    assert "no commentary of your own" in compliance_agent.SYSTEM_PROMPT
'''
p = Path("tests/test_quality.py")
if p.exists() and p.read_text(encoding="utf-8") == TEST:
    print("  already up to date: tests/test_quality.py")
else:
    p.write_text(TEST, encoding="utf-8")
    print("  wrote: tests/test_quality.py")
print("\nDone. Restart the API and the website, then run: python -m pytest")
