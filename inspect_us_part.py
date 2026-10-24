"""Read-only look at how US regulation text is laid out (to build a correct section splitter). Key never printed."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus import ingest_us as u  # noqa: E402

PKG, GID = "CFR-2024-title16-vol2", "CFR-2024-title16-vol2-part1203"
text, problem = u.fetch_part_text(PKG, GID)
print("format that worked:", u._WORKING, "| problem:", problem or "none", "| characters:", len(text))
lines = text.split("\n")
print("lines:", len(lines))
print("\n--- first 12 lines")
for line in lines[:12]:
    print(repr(line[:110]))
hits = [i for i, line in enumerate(lines) if re.match(r"\s*\u00a7\s*1203\.1[2-4]\b", line)]
print("\n--- lines that start with a section sign near 1203.12 to 1203.14:", hits[:8])
for i in hits[:3]:
    print(f"\n--- around line {i}")
    for line in lines[max(0, i - 2): i + 5]:
        print(repr(line[:110]))
starts = [line for line in lines if line.lstrip().startswith("\u00a7")]
print("\nlines that START with a section sign:", len(starts), "| first 6:", [s[:45] for s in starts[:6]])
print("section signs in the MIDDLE of lines (cross-references):", len(re.findall(r".\u00a7", text)))
print("\nDone - copy everything above (it contains no secrets) and send it to me.")
