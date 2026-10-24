"""
Ingest US federal regulations (CFR) from the GovInfo API - the FULL TEXT of each part.

    python corpus/ingest_us.py                    # CFR titles 16 and 17
    python corpus/ingest_us.py 29                 # a different title
    python corpus/ingest_us.py 16 --max-parts 20  # quick trial run

Needs GOVINFO_API_KEY in .env (free: https://www.govinfo.gov/api-signup).
Set CFR_YEAR in .env to change the annual edition (default 2024).
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote

from bs4 import BeautifulSoup
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

from api.rag.chunker import chunk_text  # noqa: E402
from corpus.common import http_get, store_chunks  # noqa: E402

BASE = "https://api.govinfo.gov"
TITLE_NAMES = {
    "16": "Commercial Practices", "17": "Commodity and Securities Exchanges",
    "26": "Internal Revenue", "29": "Labor", "45": "Public Welfare",
}
DEFAULT_TITLES = ["16", "17"]  # Titles 26/29 are huge - add them deliberately (free DB is 500 MB)


def _key() -> str:
    return os.getenv("GOVINFO_API_KEY") or "DEMO_KEY"


def _get(path: str, **params):
    return http_get(f"{BASE}{path}", params={"api_key": _key(), **params}, timeout=60)


def list_volumes(title: str, year: str) -> list:
    """Package ids like CFR-2024-title16-vol1, vol2, ... until one does not exist."""
    vols = []
    for v in range(1, 40):
        pkg = f"CFR-{year}-title{title}-vol{v}"
        if _get(f"/packages/{pkg}/summary").status_code != 200:
            break
        vols.append(pkg)
    return vols


PART_ID = re.compile(r"-part\d+[A-Za-z]*$", re.I)
PAGE_SIZE = 100


def _next_offset(data, current):
    """Where is the next page? Some responses give offsetMark directly, others only a nextPage URL."""
    nxt = data.get("offsetMark")
    if not nxt:
        m = re.search(r"offsetMark=([^&]+)", data.get("nextPage") or "")
        nxt = unquote(m.group(1)) if m else None
    return nxt if nxt and nxt != current else None


def list_granules(pkg: str):
    """
    Yield (granuleId, title) for every PART in a volume, following ALL pages.
    GovInfo also lists subparts and table-of-contents entries; those are skipped.
    """
    offset, pages, skipped, found = "*", 0, 0, 0
    seen_ids = set()
    while True:
        r = _get(f"/packages/{pkg}/granules", offsetMark=offset, pageSize=PAGE_SIZE)
        if r.status_code != 200:
            print(f"  !! GovInfo {r.status_code} listing {pkg}: {r.text[:120]}")
            break
        data = r.json()
        pages += 1
        granules = [g for g in data.get("granules", []) if g["granuleId"] not in seen_ids]
        for g in granules:
            gid = g["granuleId"]
            seen_ids.add(gid)
            if not PART_ID.search(gid):
                skipped += 1
                continue
            found += 1
            yield gid, " ".join(str(g.get("title") or gid).split())  # collapses stray control characters
        nxt = _next_offset(data, offset)
        if not granules or not nxt:
            if len(data.get("granules", [])) >= PAGE_SIZE and not nxt:
                print(f"  !! {pkg}: full page of {PAGE_SIZE} entries but no way to request the next one "
                      f"(response keys: {sorted(data)}). Some parts may be missing - send me this line.")
            break
        offset = nxt
    print(f"  [{pkg}: {found} parts found across {pages} page(s); {skipped} subpart/contents entries skipped]")


CONTENT_TYPES = ["htm", "xml", "txt"]
_WORKING = []  # content types that worked, best first - so later parts need only ONE request


def _to_text(ct, r):
    body = r.text
    if ct == "xml" or body.lstrip().startswith("<?xml"):
        return BeautifulSoup(body, "lxml-xml").get_text("\n", strip=True)
    if ct == "htm" or "<html" in body[:500].lower():
        return BeautifulSoup(body, "lxml").get_text("\n", strip=True)
    return body


def fetch_part_text(pkg: str, granule_id: str):
    """Returns (text, problem). Tries each content type; `problem` is '' on success."""
    tried = []
    for ct in _WORKING + [c for c in CONTENT_TYPES if c not in _WORKING]:
        r = _get(f"/packages/{pkg}/granules/{granule_id}/{ct}")
        if r.status_code == 200:
            text = _to_text(ct, r)
            if len(text) >= 100:
                if ct not in _WORKING:
                    _WORKING.insert(0, ct)
                return text, ""
            tried.append(f"{ct}: only {len(text)} chars")
        else:
            tried.append(f"{ct}: HTTP {r.status_code}")
    # nothing worked: ask GovInfo what it DOES offer for this part, to help diagnose
    info = ""
    sm = _get(f"/packages/{pkg}/granules/{granule_id}/summary")
    if sm.status_code == 200:
        try:
            info = " | GovInfo offers: " + ", ".join(sorted((sm.json().get("download") or {}).keys()))
        except ValueError:
            pass
    else:
        info = f" | summary HTTP {sm.status_code}"
    return "", "; ".join(tried) + info


def ingest_title(title: str, max_parts=None) -> int:
    year = os.getenv("CFR_YEAR", "2024")
    desc = TITLE_NAMES.get(title, "")
    name = f"Code of Federal Regulations Title {title}" + (f" - {desc}" if desc else "")
    print(f"\n[US] {name} ({year} edition)")
    vols = list_volumes(title, year)
    if not vols:
        print(f"  !! No volumes found for title {title}, year {year}. Check GOVINFO_API_KEY and CFR_YEAR "
              f"(that edition may not be published yet - try {int(year) - 1}).")
        return 0
    if _key() == "DEMO_KEY":
        print("  !! Using DEMO_KEY - expect rate-limit errors. Put your own GOVINFO_API_KEY in .env.")

    total, parts, seen, too_short = 0, 0, 0, 0
    problems = []
    done = False
    for pkg in vols:
        if done:
            break
        for gid, gtitle in list_granules(pkg):
            if max_parts and parts >= max_parts:
                done = True
                break
            seen += 1
            try:
                text, problem = fetch_part_text(pkg, gid)
            except RuntimeError as e:  # network down, or GovInfo rate limit (HTTP 429)
                why = "GovInfo rate limit reached" if "429" in str(e) else "GovInfo stopped responding"
                print(f"  !! {why} ({str(e)[:90]}). Wait a while (the limit resets hourly), then re-run the same "
                      "command - parts already stored are skipped.")
                done = True
                break
            time.sleep(0.4)  # be polite to the API
            if problem:
                problems.append(f"{gid}: {problem}")
                if len(problems) <= 3:
                    print(f"  !! could not fetch {gid} - {problem}")
                continue
            if len(text) < 100:
                too_short += 1
                continue
            parts += 1
            chunks = chunk_text(text, name, "US", int(year), "regulation", fallback_section=gtitle[:120])
            inserted, _ = store_chunks(chunks)
            total += inserted
            print(f"  part {parts}: {gtitle[:60]} -> {inserted} new chunks", flush=True)
    if not parts:
        print(f"  XX No part text was retrieved - nothing stored.\n"
              f"     volumes found: {len(vols)} | parts listed: {seen} | fetch failures: {len(problems)} | "
              f"too short: {too_short}")
        if seen == 0:
            print("     GovInfo listed NO parts for these volumes (the listing response shape may differ).")
        print("     Run:  python scripts/diagnose_govinfo.py   and send me its output.")
        return 0
    print(f"  OK {name}: {total} new chunks from {parts} parts")
    return total


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("titles", nargs="*", default=DEFAULT_TITLES)
    ap.add_argument("--max-parts", type=int, default=None, help="stop after N parts (trial run)")
    a = ap.parse_args()
    grand = sum(ingest_title(t, a.max_parts) for t in a.titles)
    print(f"\nOK US corpus: {grand:,} new chunks stored")
