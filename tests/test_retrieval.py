"""
LIVE retrieval-quality test over the golden sets in tests/golden/.
    python tests/test_retrieval.py
    KEJI_LIVE=1 pytest tests/test_retrieval.py

Metrics: Precision@5 (share of top-5 chunks containing the expected keyword) and
Recall@5 (is the expected statute in the top 5?). Targets: P ≥ 0.60, R ≥ 0.70.
Jurisdictions with no rows in the database are SKIPPED, not failed.
"""
import json
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

GOLDEN_DIR = Path(__file__).parent / "golden"
P_TARGET, R_TARGET = 0.60, 0.70


def precision_at_k(results, keyword, k=5):
    top = results[:k]
    hits = sum(1 for r in top if keyword.lower() in (r.get("statute_name", "") + " " + r.get("content", "")).lower())
    return hits / k


def recall_at_k(results, statute, k=5):
    return 1.0 if any(statute.lower() in r.get("statute_name", "").lower() for r in results[:k]) else 0.0


def run_golden_set(path: Path) -> dict:
    from api.rag.retriever import retrieve

    g = json.loads(path.read_text())
    jx = g["jurisdiction"]
    print(f"\n🧪 {path.name} — {jx}, {len(g['queries'])} queries")
    print(f"{'ID':<8}{'P@5':<7}{'R@5':<7}Top statute")
    ps, rs, empty = [], [], 0
    for q in g["queries"]:
        res = retrieve(q["query"], jx)
        if not res:
            empty += 1
            print(f"{q['id']:<8}{'-':<7}{'-':<7}NO RESULTS")
            continue
        p, r = precision_at_k(res, q["expected_section_keyword"]), recall_at_k(res, q["expected_statute"])
        ps.append(p); rs.append(r)
        print(f"{q['id']:<8}{p:<7.2f}{r:<7.2f}{res[0]['statute_name'][:45]}")
    if not ps:
        return {"jurisdiction": jx, "status": "SKIPPED"}
    mp, mr = sum(ps) / len(ps), sum(rs) / len(rs)
    ok = mp >= P_TARGET and mr >= R_TARGET
    return {"jurisdiction": jx, "precision": mp, "recall": mr, "status": "PASS" if ok else "FAIL"}


@pytest.mark.live
@pytest.mark.parametrize("path", sorted(GOLDEN_DIR.glob("*.json")), ids=lambda p: p.stem)
def test_golden(path):
    r = run_golden_set(path)
    if r["status"] == "SKIPPED":
        pytest.skip(f"{r['jurisdiction']} corpus not loaded")
    assert r["status"] == "PASS", f"{r}"


if __name__ == "__main__":
    results = [run_golden_set(p) for p in sorted(GOLDEN_DIR.glob("*.json"))]
    print("\n" + "=" * 50 + "\nOVERALL RETRIEVAL QUALITY\n" + "=" * 50)
    for r in results:
        if r["status"] == "SKIPPED":
            print(f"  {r['jurisdiction']}: ⏭  SKIPPED (corpus not loaded)")
        else:
            print(f"  {r['jurisdiction']}: P={r['precision']:.2f} R={r['recall']:.2f}  "
                  f"{'✅ PASS' if r['status'] == 'PASS' else '❌ FAIL'}")
    print(f"\nTargets: Precision@5 ≥ {P_TARGET}, Recall@5 ≥ {R_TARGET}")
    sys.exit(1 if any(r["status"] == "FAIL" for r in results) else 0)
