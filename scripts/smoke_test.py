"""
END-TO-END smoke test against a RUNNING API (local or deployed).

    python scripts/smoke_test.py                                   # http://localhost:8000
    python scripts/smoke_test.py --base https://api.keji.legal
    python scripts/smoke_test.py --base https://api.keji.legal --approve   # also tests the reviewer flow

Reads KEJI_API_SECRET (and KEJI_REVIEWER_SECRET for --approve) from .env or the environment.
Exit code 0 = everything passed.
"""
import argparse
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()
failures = []


def check(name, ok, detail=""):
    print(f"  {'✅' if ok else '❌'} {name}" + (f"  — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.getenv("KEJI_API_BASE_URL", "http://localhost:8000"))
    ap.add_argument("--jurisdiction", default="UK")
    ap.add_argument("--query", default="What are a director's duties?")
    ap.add_argument("--approve", action="store_true", help="also approve the check (needs KEJI_REVIEWER_SECRET)")
    a = ap.parse_args()
    base = a.base.rstrip("/")
    secret, reviewer = os.getenv("KEJI_API_SECRET", ""), os.getenv("KEJI_REVIEWER_SECRET", "")
    auth = {"Authorization": f"Bearer {secret}"} if secret else {}
    print(f"\nKEJI smoke test → {base}\n")

    r = requests.get(f"{base}/health", timeout=15)
    check("GET /health returns ok", r.status_code == 200 and r.json().get("status") == "ok", r.text[:100])

    r = requests.post(f"{base}/jurisdiction/classify", json={"text": "GDPR breach notification"}, headers=auth, timeout=60)
    check("POST /jurisdiction/classify → EU", r.status_code == 200 and r.json().get("suggestion") == "EU", f"{r.status_code} {r.text[:120]}")

    r = requests.post(f"{base}/compliance/check", json={"query": "x"}, headers=auth, timeout=30)
    check("bad input rejected (422)", r.status_code == 422, str(r.status_code))

    r = requests.post(f"{base}/compliance/check", json={"query": a.query, "jurisdiction": a.jurisdiction}, timeout=90)
    if r.status_code == 401:
        check("request WITHOUT a token is refused (production behaviour)", True)
    else:
        print("  ℹ️  API accepted a tokenless call — fine for development, NOT for production.")

    r = requests.post(f"{base}/compliance/check", json={"query": a.query, "jurisdiction": a.jurisdiction}, headers=auth, timeout=120)
    ok = r.status_code == 200
    check("POST /compliance/check succeeds", ok, f"{r.status_code} {r.text[:200]}")
    if ok:
        d = r.json()
        print(f"     status={d['status']}  citations={len(d['citations'])}  check_id={d.get('check_id')}")
        check("result is pending_review", d.get("review_status") == "pending_review")
        check("check was saved (check_id returned)", bool(d.get("check_id")))
        if d["status"] == "NO_RESULTS":
            print("  ⚠️  NO_RESULTS — is the corpus ingested for this jurisdiction? (python corpus/ingest.py)")
        else:
            check("citations were retrieved", len(d["citations"]) > 0)
        if d.get("check_id"):
            s = requests.get(f"{base}/compliance/{d['check_id']}/status", headers=auth, timeout=30)
            check("status endpoint says pending_review", s.status_code == 200 and s.json().get("status") == "pending_review", s.text[:100])
            if a.approve:
                rh = {**auth, "X-Reviewer-Key": reviewer}
                if secret:
                    no_key = requests.put(f"{base}/compliance/{d['check_id']}/approve", json={}, headers=auth, timeout=30)
                    check("approve WITHOUT reviewer key is refused", no_key.status_code in (403, 503) or not reviewer, str(no_key.status_code))
                ap_r = requests.put(f"{base}/compliance/{d['check_id']}/approve", json={"reviewer_note": "smoke test"}, headers=rh, timeout=30)
                check("approve WITH reviewer key works", ap_r.status_code == 200, f"{ap_r.status_code} {ap_r.text[:100]}")
                again = requests.put(f"{base}/compliance/{d['check_id']}/approve", json={}, headers=rh, timeout=30)
                check("approving twice is blocked (409)", again.status_code == 409, str(again.status_code))

    r = requests.post(f"{base}/contracts/analyze", headers=auth, timeout=90, json={
        "clause": "The Supplier shall indemnify and hold harmless the Customer.", "jurisdiction": a.jurisdiction})
    check("POST /contracts/analyze works", r.status_code == 200 and r.json().get("flags") is not None, f"{r.status_code} {r.text[:120]}")

    print(f"\n{'ALL CHECKS PASSED ✅' if not failures else f'{len(failures)} CHECK(S) FAILED ❌: ' + ', '.join(failures)}\n")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
