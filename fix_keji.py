# fix_keji.py - applies the latest KEJI fixes to your files. Safe to run more than once.
from pathlib import Path
import sys

ROOT = Path(".")
if not (ROOT / "corpus" / "common.py").exists():
    sys.exit("Run this from inside the keji-legal folder (the one that contains corpus and api).")


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel, text, backup=True):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if backup and p.exists():
        Path(str(p) + ".bak").write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    p.write_text(text, encoding="utf-8")


def put(rel, text, backup=True):
    """Write a whole file, but only if it would actually change."""
    p = ROOT / rel
    if p.exists() and p.read_text(encoding="utf-8") == text:
        print(f"  already up to date: {rel}")
        return
    write(rel, text, backup)
    print(f"  wrote: {rel}")


def edit(rel, old, new, marker):
    s = read(rel)
    if marker in s:
        print(f"  already up to date: {rel} ({marker})")
        return
    if old not in s:
        print(f"  !! could not patch {rel} - its text differs from what I expected. Tell me.")
        return
    write(rel, s.replace(old, new, 1))
    print(f"  patched: {rel} ({marker})")


# ---- 1. corpus/common.py : retry on network timeouts ------------------------------------
edit("corpus/common.py", "import requests\n", "import httpx\nimport requests\n", "import httpx")

HELPER = '''def with_retry(fn, attempts=6, base_delay=3.0):
    """Run fn(); on a NETWORK error wait and try again (3s, 6s, 9s...). Other errors are raised at once."""
    last = None
    for i in range(attempts):
        try:
            return fn()
        except (httpx.TransportError, OSError) as e:
            last = e
            if i == attempts - 1:
                break
            wait = base_delay * (i + 1)
            print(f"    !! network problem ({type(e).__name__}); retrying in {wait:.0f}s [{i + 1}/{attempts - 1}]", flush=True)
            time.sleep(wait)
    raise RuntimeError(
        f"Network kept failing after {attempts} tries ({type(last).__name__}). Check your internet/VPN, "
        "then simply re-run the same command - chunks already stored are skipped automatically."
    ) from last


def sanity_check('''
edit("corpus/common.py", "def sanity_check(", HELPER, "def with_retry")

edit(
    "corpus/common.py",
    '''        res = db.table("statute_chunks").upsert(
            rows, on_conflict="jurisdiction,content_hash", ignore_duplicates=True
        ).execute()''',
    '''        res = with_retry(lambda: db.table("statute_chunks").upsert(
            rows, on_conflict="jurisdiction,content_hash", ignore_duplicates=True
        ).execute())''',
    "with_retry(lambda",
)

# ---- 2. corpus/parsers.py : silence the harmless XML-as-HTML warning ---------------------
edit(
    "corpus/parsers.py",
    "import re\n\nfrom bs4 import BeautifulSoup\n",
    "import re\nimport warnings\n\nfrom bs4 import BeautifulSoup, XMLParsedAsHTMLWarning\n\n"
    "# EU files are XHTML; the HTML parser handles them fine, so silence the notice.\n"
    'warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)\n',
    "XMLParsedAsHTMLWarning",
)

# ---- 3. corpus/ingest_us.py : explains WHY nothing was retrieved (whole file replaced) ----
INGEST_US = r'''"""
Ingest US federal regulations (CFR) from the GovInfo API - the FULL TEXT of each part.

    python corpus/ingest_us.py                    # CFR titles 16 and 17
    python corpus/ingest_us.py 29                 # a different title
    python corpus/ingest_us.py 16 --max-parts 20  # quick trial run

Needs GOVINFO_API_KEY in .env (free: https://www.govinfo.gov/api-signup).
Set CFR_YEAR in .env to change the annual edition (default 2024).
"""
import argparse
import os
import sys
import time
from pathlib import Path

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


def list_granules(pkg: str):
    """Yield (granuleId, title) for every part in a volume."""
    offset = "*"
    while True:
        r = _get(f"/packages/{pkg}/granules", offsetMark=offset, pageSize=100)
        if r.status_code != 200:
            print(f"  !! GovInfo {r.status_code} listing {pkg}: {r.text[:120]}")
            return
        data = r.json()
        for g in data.get("granules", []):
            yield g["granuleId"], g.get("title", g["granuleId"])
        offset = data.get("offsetMark")
        if not data.get("granules") or not offset or not data.get("nextPage"):
            return


def fetch_part_text(pkg: str, granule_id: str):
    """Returns (text, problem). `problem` is '' on success, else a short explanation."""
    r = _get(f"/packages/{pkg}/granules/{granule_id}/htm")
    if r.status_code != 200:
        return "", f"HTTP {r.status_code}: {r.text[:100]!r}"
    return BeautifulSoup(r.text, "lxml").get_text("\n", strip=True), ""


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
            text, problem = fetch_part_text(pkg, gid)
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
'''
put("corpus/ingest_us.py", INGEST_US)

# ---- 4. scripts/diagnose_govinfo.py : shows exactly what GovInfo returns ------------------
DIAG = r'''"""Diagnose US (GovInfo) access. Your API key is never printed.   python scripts/diagnose_govinfo.py"""
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

KEY = os.getenv("GOVINFO_API_KEY") or ""
YEAR = os.getenv("CFR_YEAR", "2024")
PKG = f"CFR-{YEAR}-title16-vol1"
BASE = "https://api.govinfo.gov"
H = {"User-Agent": "KEJI Legal Research/0.1"}
K = KEY or "DEMO_KEY"


def clean(t):
    return t.replace(KEY, "<KEY>") if KEY else t


def show(label, r, n=300):
    print(f"\n-- {label}")
    print(f"   status: {r.status_code} | type: {r.headers.get('content-type', '?')} | size: {len(r.content)} bytes")
    print(f"   rate-limit remaining: {r.headers.get('x-ratelimit-remaining', 'n/a')}")
    print(f"   body starts: {clean(r.text[:n])!r}")


print("GovInfo diagnostic")
print(f"  GOVINFO_API_KEY: {'set (' + str(len(KEY)) + ' characters)' if KEY else 'NOT SET -> DEMO_KEY will be used'}")
print(f"  CFR_YEAR: {YEAR}   package tested: {PKG}")
try:
    r = requests.get(f"{BASE}/packages/{PKG}/summary", params={"api_key": K}, headers=H, timeout=60)
    show("1. package summary", r)

    r = requests.get(f"{BASE}/packages/{PKG}/granules", params={"api_key": K, "offsetMark": "*", "pageSize": 5},
                     headers=H, timeout=60)
    show("2. list granules (first 5)", r, 200)
    gid = None
    if r.status_code == 200:
        data = r.json()
        print(f"   JSON keys: {list(data)}")
        gl = data.get("granules") or []
        print(f"   granules in this page: {len(gl)}")
        if gl:
            print("   first granule: " + json.dumps({k: gl[0][k] for k in list(gl[0])[:6]}, indent=2))
            gid = gl[0].get("granuleId")
    if gid:
        for ct in ("htm", "xml"):
            r = requests.get(f"{BASE}/packages/{PKG}/granules/{gid}/{ct}", params={"api_key": K}, headers=H, timeout=90)
            show(f"3. granule text as .{ct}  ({gid})", r, 250)
    else:
        print("\n-- 3. skipped (no granule id available)")

    bulk = f"https://www.govinfo.gov/bulkdata/CFR/{YEAR}/title-16/{PKG}.xml"
    r = requests.get(bulk, headers=H, timeout=90, stream=True)
    head = next(r.iter_content(400), b"")
    r.close()
    print(f"\n-- 4. bulk-data file (no API key needed)\n   {bulk}\n   status: {r.status_code} | type: "
          f"{r.headers.get('content-type', '?')} | size: {r.headers.get('content-length', 'unknown')} bytes\n"
          f"   starts: {head[:250]!r}")
except Exception as e:
    print(f"\nXX Network error: {type(e).__name__}: {clean(str(e))[:200]}")
print("\nDone - copy everything above (it contains no secrets) and send it to me.")
'''
put("scripts/diagnose_govinfo.py", DIAG, backup=False)
print("\nAll fixes applied.")
