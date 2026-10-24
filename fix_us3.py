# fix_us3.py - US ingester: follow ALL pages of GovInfo's part listing + clean odd characters in titles.
from pathlib import Path
import re
import sys

p = Path("corpus/ingest_us.py")
if not p.exists():
    sys.exit("Run this from inside the keji-legal folder.")
s = p.read_text(encoding="utf-8")
if "_next_offset" in s:
    print("  already up to date: corpus/ingest_us.py")
    sys.exit(0)

if "from urllib.parse import unquote" not in s:
    s = s.replace("from pathlib import Path\n", "from pathlib import Path\nfrom urllib.parse import unquote\n", 1)
if "\nimport re\n" not in s:
    s = s.replace("import argparse\nimport os\n", "import argparse\nimport os\nimport re\n", 1)

NEW_LIST = '''PART_ID = re.compile(r"-part\\d+[A-Za-z]*$", re.I)
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


'''
pat = re.compile(r"(?:PART_ID = .*?\n)?(?:NON_PART_SKIPPED = .*?\n)?\n*def list_granules\(pkg: str\):.*?(?=def fetch_part_text|CONTENT_TYPES = )", re.S)
if not pat.search(s):
    sys.exit("  !! could not find list_granules in corpus/ingest_us.py - send me the first 80 lines of that file.")
s = pat.sub(lambda m: NEW_LIST, s, count=1)

Path(str(p) + ".bak3").write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
p.write_text(s, encoding="utf-8")
print("  patched: corpus/ingest_us.py (follows every page; cleans titles)")
