"""Adds UK GDPR and the main UK contract-law statutes. Safe to re-run (duplicates are skipped)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus.ingest import ingest_uk  # noqa: E402

MORE = [  # (year, type, number, name, a word that must appear in the real document)
    (2016, "eur", 679, "UK General Data Protection Regulation", "personal data"),
    (1977, "ukpga", 50, "Unfair Contract Terms Act 1977", "negligence"),
    (2015, "ukpga", 15, "Consumer Rights Act 2015", "consumer"),
    (1967, "ukpga", 7, "Misrepresentation Act 1967", "misrepresentation"),
    (1998, "ukpga", 20, "Late Payment of Commercial Debts (Interest) Act 1998", "interest"),
    (1999, "ukpga", 31, "Contracts (Rights of Third Parties) Act 1999", "third party"),
    (1979, "ukpga", 54, "Sale of Goods Act 1979", "goods"),
    (1982, "ukpga", 29, "Supply of Goods and Services Act 1982", "services"),
    (1996, "ukpga", 23, "Arbitration Act 1996", "arbitration"),
]

total = 0
for args in MORE:
    total += ingest_uk(*args)
print(f"\nDone - {total:,} new chunks stored. Each law should show a 'new chunks stored' line;")
print("a 'SANITY FAIL' line means that law was NOT stored - send me that line.")
