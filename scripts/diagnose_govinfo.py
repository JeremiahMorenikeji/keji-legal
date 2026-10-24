"""Diagnose US (GovInfo) access. Your API key is never printed.   python scripts/diagnose_govinfo.py"""
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
