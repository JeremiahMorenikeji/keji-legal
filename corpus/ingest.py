"""
Ingest UK, Canadian and EU legislation into Supabase.

    python corpus/ingest.py            # everything
    python corpus/ingest.py uk         # just the UK
    python corpus/ingest.py ca eu      # a selection

Safe to re-run: duplicates are skipped. Watch for ✅ (success) and ⛔ (sanity
check failed — that statute was NOT stored and needs a manual look).
"""
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.rag.chunker import chunk_text  # noqa: E402
from corpus.common import ROOT, USER_AGENT, http_get, sanity_check, save_and_load, store_chunks  # noqa: E402
from corpus.parsers import parse_clml, parse_eu_html, parse_justice_laws  # noqa: E402


def _chunk_sections(sections, name, jurisdiction, year, corpus_type="statute"):
    chunks = []
    for ref, text in sections:
        chunks += chunk_text(text, name, jurisdiction, year, corpus_type,
                             section=None if ref == "full_text" else ref)
    return chunks


def _finish(name, chunks):
    inserted, skipped = store_chunks(chunks)
    print(f"  ✅ {name}: {inserted} new chunks stored ({skipped} already present)")
    return inserted


# ── UK ───────────────────────────────────────────────────────────────────────
def ingest_uk(year: int, act_type: str, number: int, name: str, marker: str) -> int:
    print(f"\n🇬🇧 {name}")
    path = ROOT / "corpus/statutes/UK" / f"{name.replace(' ', '_')}.xml"
    data = save_and_load(f"https://www.legislation.gov.uk/{act_type}/{year}/{number}/data.xml", path)
    if not data:
        return 0
    sections = parse_clml(data)
    print(f"  parsed {len(sections)} provisions")
    if not sanity_check(" ".join(f"{r} {t}" for r, t in sections), marker, name):
        return 0
    return _finish(name, _chunk_sections(sections, name, "UK", year))


# ── Canada ───────────────────────────────────────────────────────────────────
def ingest_ca(act_id: str, name: str, marker: str) -> int:
    print(f"\n🇨🇦 {name}")
    path = ROOT / "corpus/statutes/CA" / f"{name.replace(' ', '_')}.xml"
    data = save_and_load(f"https://laws-lois.justice.gc.ca/eng/XML/{act_id}.xml", path)
    if not data:
        return 0
    sections = parse_justice_laws(data)
    print(f"  parsed {len(sections)} provisions")
    if not sanity_check(" ".join(f"{r} {t}" for r, t in sections), marker, name):
        return 0
    return _finish(name, _chunk_sections(sections, name, "CA", None))


# ── EU ───────────────────────────────────────────────────────────────────────
def fetch_eu(celex: str) -> str:
    """
    Try, in order: (1) CELLAR content negotiation, (2) CELLAR SPARQL lookup,
    (3) the EUR-Lex page. Each can be blocked or change shape, so every step is
    guarded; you can always save the page by hand (see save_and_load).
    """
    attempts = []

    def negotiation():
        r = http_get(f"https://publications.europa.eu/resource/celex/{celex}",
                     headers={"Accept": "application/xhtml+xml", "Accept-Language": "eng"},
                     allow_redirects=True, timeout=90)
        return r.text if r.status_code == 200 else ""

    def sparql():
        q = f"""PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT ?file WHERE {{ ?work cdm:resource_legal_id_celex "{celex}"^^<http://www.w3.org/2001/XMLSchema#string> .
 ?expr cdm:expression_belongs_to_work ?work ; cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/ENG> .
 ?mani cdm:manifestation_manifests_expression ?expr ; cdm:manifestation_type "xhtml"^^<http://www.w3.org/2001/XMLSchema#string> .
 BIND(STR(?mani) AS ?file) }} LIMIT 1"""
        r = http_get("https://publications.europa.eu/webapi/rdf/sparql", params={"query": q},
                     headers={"Accept": "application/sparql-results+json"})
        rows = r.json().get("results", {}).get("bindings", []) if r.status_code == 200 else []
        return http_get(rows[0]["file"]["value"], headers={"Accept": "application/xhtml+xml"}).text if rows else ""

    def eurlex():
        return http_get(f"https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{celex}",
                        headers={"Accept": "text/html"}, timeout=90).text

    for label, fn in (("CELLAR content negotiation", negotiation), ("CELLAR SPARQL", sparql), ("EUR-Lex page", eurlex)):
        try:
            html = fn()
            if html and len(html) > 5000:
                print(f"  fetched via {label}")
                return html
            attempts.append(f"{label}: too short")
        except Exception as e:  # noqa: BLE001
            attempts.append(f"{label}: {e}")
    print("  ⚠ all EU fetch methods failed: " + " | ".join(attempts))
    return ""


def ingest_eu(celex: str, name: str, year: int, marker: str) -> int:
    print(f"\n🇪🇺 {name} (CELEX {celex})")
    path = ROOT / "corpus/statutes/EU" / f"{name.replace(' ', '_')}.html"
    html = ""
    if path.exists() and path.stat().st_size > 5000:
        print(f"  using local file {path}")
        html = path.read_text(encoding="utf-8", errors="ignore")
    else:
        html = fetch_eu(celex)
        if html:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(html, encoding="utf-8")
    if not html:
        print(f"  Tip: open https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:{celex} in your "
              f"browser, save the page as {path}, and re-run.")
        return 0
    sections = parse_eu_html(html)
    print(f"  parsed {len(sections)} articles")
    if not sanity_check(" ".join(f"{r} {t}" for r, t in sections), marker, name):
        return 0
    return _finish(name, _chunk_sections(sections, name, "EU", year, "regulation"))


# ── What to ingest ───────────────────────────────────────────────────────────
UK_CORPUS = [  # (year, type, number, name, sanity marker)
    (2006, "ukpga", 46, "Companies Act 2006", "director"),
    (2018, "ukpga", 12, "Data Protection Act 2018", "personal data"),
    (1996, "ukpga", 18, "Employment Rights Act 1996", "unfair dismissal"),
    (1988, "ukpga", 48, "Copyright Designs and Patents Act 1988", "copyright"),
]
CA_CORPUS = [  # (Justice Laws id, name, sanity marker)
    ("C-44", "Canada Business Corporations Act", "director"),
    ("P-8.6", "Personal Information Protection and Electronic Documents Act", "consent"),
    ("C-34", "Competition Act", "competition"),
]
EU_CORPUS = [  # (CELEX, name, year, sanity marker)
    ("32016R0679", "General Data Protection Regulation", 2016, "Article 1"),
    ("32022R0868", "EU Data Governance Act", 2022, "Article 1"),
]


def main(targets: list[str]) -> int:
    targets = [t.lower() for t in targets] or ["uk", "ca", "eu"]
    unknown = set(targets) - {"uk", "ca", "eu"}
    if unknown:
        print(f"Unknown target(s): {unknown}. Use: uk ca eu")
        return 2
    total = 0
    if "uk" in targets:
        for args in UK_CORPUS: total += ingest_uk(*args)
    if "ca" in targets:
        for args in CA_CORPUS: total += ingest_ca(*args)
    if "eu" in targets:
        for args in EU_CORPUS: total += ingest_eu(*args)
    print(f"\n{'=' * 60}\n✅ INGESTION COMPLETE — {total:,} new chunks stored")
    print("   Next: python tests/test_retrieval.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
