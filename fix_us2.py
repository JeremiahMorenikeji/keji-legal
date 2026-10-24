# fix_us2.py - US ingester: try htm / xml / txt for each part, remember what works, handle rate limits.
from pathlib import Path
import re
import sys

p = Path("corpus/ingest_us.py")
if not p.exists():
    sys.exit("Run this from inside the keji-legal folder.")
s = p.read_text(encoding="utf-8")
if "_WORKING" in s:
    print("  already up to date: corpus/ingest_us.py")
    sys.exit(0)

NEW_FETCH = '''CONTENT_TYPES = ["htm", "xml", "txt"]
_WORKING = []  # content types that worked, best first - so later parts need only ONE request


def _to_text(ct, r):
    body = r.text
    if ct == "xml" or body.lstrip().startswith("<?xml"):
        return BeautifulSoup(body, "lxml-xml").get_text("\\n", strip=True)
    if ct == "htm" or "<html" in body[:500].lower():
        return BeautifulSoup(body, "lxml").get_text("\\n", strip=True)
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


'''
pat = re.compile(r"def fetch_part_text\(.*?(?=def ingest_title)", re.S)
if not pat.search(s):
    sys.exit("  !! could not find fetch_part_text in corpus/ingest_us.py - send me the first 80 lines of that file.")
s = pat.sub(lambda m: NEW_FETCH, s, count=1)

OLD_CALL = "            text, problem = fetch_part_text(pkg, gid)\n"
NEW_CALL = '''            try:
                text, problem = fetch_part_text(pkg, gid)
            except RuntimeError as e:  # network down, or GovInfo rate limit (HTTP 429)
                why = "GovInfo rate limit reached" if "429" in str(e) else "GovInfo stopped responding"
                print(f"  !! {why} ({str(e)[:90]}). Wait a while (the limit resets hourly), then re-run the same "
                      "command - parts already stored are skipped.")
                done = True
                break
'''
if OLD_CALL not in s:
    sys.exit("  !! could not find the fetch call in ingest_title - send me lines 80-130 of corpus/ingest_us.py")
s = s.replace(OLD_CALL, NEW_CALL, 1)

Path(str(p) + ".bak2").write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
p.write_text(s, encoding="utf-8")
print("  patched: corpus/ingest_us.py (tries htm/xml/txt, remembers what works, handles rate limits)")
