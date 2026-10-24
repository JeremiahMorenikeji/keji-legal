# fix_us.py - make the US ingester skip table-of-contents / chapter entries. Safe to run twice.
from pathlib import Path
import re
import sys

p = Path("corpus/ingest_us.py")
if not p.exists():
    sys.exit("Run this from inside the keji-legal folder.")
s = p.read_text(encoding="utf-8")

if "NON_PART_SKIPPED" in s:
    print("  already up to date: corpus/ingest_us.py")
    sys.exit(0)

if "import re\n" not in s:
    s = s.replace("import argparse\nimport os\n", "import argparse\nimport os\nimport re\n", 1)

NEW_FUNC = '''PART_ID = re.compile(r"-part\\d+[A-Za-z]*$", re.I)
NON_PART_SKIPPED = []  # filled while listing, just for the message below


def list_granules(pkg: str):
    """
    Yield (granuleId, title) for every PART in a volume.
    GovInfo also lists table-of-contents and chapter entries (e.g. ...-toc-id2, ...-chapI);
    those have no text (HTTP 400), so they are skipped.
    """
    offset = "*"
    while True:
        r = _get(f"/packages/{pkg}/granules", offsetMark=offset, pageSize=100)
        if r.status_code != 200:
            print(f"  !! GovInfo {r.status_code} listing {pkg}: {r.text[:120]}")
            return
        data = r.json()
        skipped = 0
        for g in data.get("granules", []):
            gid = g["granuleId"]
            if not PART_ID.search(gid):
                skipped += 1
                NON_PART_SKIPPED.append(gid)
                continue
            yield gid, g.get("title", gid)
        if skipped:
            print(f"  (skipped {skipped} table-of-contents/chapter entries, e.g. {NON_PART_SKIPPED[-1]})")
        offset = data.get("offsetMark")
        if not data.get("granules") or not offset or not data.get("nextPage"):
            return


'''
pat = re.compile(r"def list_granules\(pkg: str\):.*?(?=def fetch_part_text)", re.S)
if not pat.search(s):
    sys.exit("  !! could not find list_granules in corpus/ingest_us.py - send me the first 60 lines of that file.")
s = pat.sub(lambda m: NEW_FUNC, s, count=1)
Path(str(p) + ".bak").write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
p.write_text(s, encoding="utf-8")
print("  patched: corpus/ingest_us.py (only PART entries are fetched now)")
