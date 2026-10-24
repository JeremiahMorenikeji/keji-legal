"""
Ingestion tests use SYNTHETIC fixtures shaped like the real formats (CLML, Justice Laws XML,
EU XHTML). They prove the parsing/storing logic; the final proof is a live run of
`python corpus/ingest.py` against the real sites.
"""
import numpy as np
import pytest

from corpus import common, ingest, ingest_us
from corpus.parsers import parse_clml, parse_eu_html, parse_justice_laws

CLML = b"""<?xml version="1.0"?>
<Legislation xmlns="http://www.legislation.gov.uk/namespaces/legislation">
 <Primary><Body>
  <P1group><Title>Duty to promote the success of the company</Title>
   <P1 id="section-172"><Pnumber>172</Pnumber>
    <P1para><P2 id="section-172-1"><Pnumber>1</Pnumber><P2para>A director of a company must act in the way he considers,
    in good faith, would be most likely to promote the success of the company for the benefit of its members as a whole.</P2para></P2></P1para></P1>
  </P1group>
  <P1group><Title>Duty to exercise independent judgment</Title>
   <P1 id="section-173"><Pnumber>173</Pnumber><P1para><Text>A director of a company must exercise independent judgment.
    <CommentaryRef Ref="c1"/></Text></P1para></P1>
  </P1group>
  <P1group><Title>Tiny</Title><P1 id="section-9"><Pnumber>9</Pnumber><P1para>x</P1para></P1></P1group>
 </Body></Primary>
 <Commentaries><Commentary id="c1" Type="F"><Para><Text>Words substituted by SI 2020/1</Text></Para></Commentary></Commentaries>
</Legislation>"""

JL = b"""<?xml version="1.0"?>
<Statute><Body><Heading><Label>PART X</Label></Heading>
 <Section id="s122"><MarginalNote>Duty of care</MarginalNote><Label>122</Label>
  <Text>Every director and officer of a corporation shall act honestly and in good faith with a view to the best interests of the corporation.</Text>
  <Subsection><Label>(2)</Label><Text>Every director shall exercise the care, diligence and skill of a reasonably prudent person.</Text></Subsection>
 </Section></Body></Statute>"""

EU_ART_IDS = """<html><body>
 <div class="eli-subdivision" id="art_1"><p>Article 1</p><p>Subject-matter and objectives. This Regulation lays down rules relating to the protection of natural persons.</p></div>
 <div class="eli-subdivision" id="art_5"><p>Article 5</p><p>Principles relating to processing of personal data. Personal data shall be processed lawfully.</p>
   <div id="art_5.tit_1">nested should be ignored by the id pattern</div></div>
</body></html>"""

EU_PLAIN = """<html><body>
<p>Article 1</p><p>Subject-matter and objectives. This Regulation lays down rules relating to the protection of natural persons.</p>
<p>Article 2</p><p>Material scope. This Regulation applies to the processing of personal data wholly or partly by automated means.</p>
</body></html>"""


def test_clml_sections_titles_and_noise_removed():
    s = dict(parse_clml(CLML))
    assert set(s) == {"Section 172", "Section 173"}                    # stub section 9 dropped
    assert s["Section 172"].startswith("Duty to promote the success of the company.")
    assert "success of the company" in s["Section 172"]
    assert "substituted by SI" not in " ".join(s.values())              # editorial commentary stripped


def test_clml_unknown_structure_falls_back_to_full_text():
    assert parse_clml(b"<Legislation><Para>Some unexpected structure but real content here.</Para></Legislation>")[0][0] == "full_text"


def test_justice_laws_sections():
    out = parse_justice_laws(JL)
    assert out[0][0] == "Section 122"
    assert out[0][1].startswith("Duty of care.") and "reasonably prudent person" in out[0][1]


def test_eu_by_id_and_by_text_fallback():
    by_id = parse_eu_html(EU_ART_IDS)
    assert [r for r, _ in by_id] == ["Article 1", "Article 5"]
    plain = parse_eu_html(EU_PLAIN)
    assert [r for r, _ in plain] == ["Article 1", "Article 2"]
    assert "Material scope" in plain[1][1] and "Material scope" not in plain[0][1]


def test_sanity_check_catches_challenge_page_and_wrong_doc(capsys):
    assert not common.sanity_check("<html>Just a moment... Checking your browser</html>", "Article 1", "GDPR")
    assert not common.sanity_check("x" * 3000, "Article 1", "GDPR")           # long but wrong content
    assert common.sanity_check("Article 1 " + "x" * 3000, "Article 1", "GDPR")


# ── storing ─────────────────────────────────────────────────────────────────
def _chunks(n, prefix="text"):
    return [{"jurisdiction": "UK", "corpus_type": "statute", "statute_name": "Act", "section": f"Section {i}",
             "year": 2006, "content": f"{prefix} {i}", "metadata": {}} for i in range(n)]


def test_store_chunks_batches_and_dedupes(fake_db):
    embed = lambda texts: np.zeros((len(texts), 384))
    ins, skipped = common.store_chunks(_chunks(150), embed=embed, db=fake_db, batch=64)
    assert (ins, skipped) == (150, 0) and len(fake_db.store["statute_chunks"]) == 150
    ins2, skipped2 = common.store_chunks(_chunks(150), embed=embed, db=fake_db)      # re-run = no duplicates
    assert (ins2, skipped2) == (0, 150) and len(fake_db.store["statute_chunks"]) == 150
    row = fake_db.store["statute_chunks"][0]
    assert len(row["embedding"]) == 384 and row["jurisdiction"] == "UK"


def test_ingest_uk_end_to_end_with_fake_network(fake_db, monkeypatch, tmp_path):
    big = CLML.replace(b"x</P1para>", b"y</P1para>")
    long_text = b"A director of a company must do the right thing. " * 60
    big = CLML.replace(b"must exercise independent judgment.", b"must exercise independent judgment. " + long_text)
    monkeypatch.setattr(ingest, "ROOT", tmp_path)
    monkeypatch.setattr(ingest, "save_and_load", lambda url, path, **kw: big)
    monkeypatch.setattr(ingest, "store_chunks", lambda chunks: common.store_chunks(chunks, db=fake_db, embed=lambda t: np.zeros((len(t), 384))))
    n = ingest.ingest_uk(2006, "ukpga", 46, "Companies Act 2006", "director")
    rows = fake_db.store["statute_chunks"]
    assert n == len(rows) > 0
    assert {r["section"] for r in rows} == {"Section 172", "Section 173"}      # real pinpoint citations
    assert all(r["statute_name"] == "Companies Act 2006" and r["jurisdiction"] == "UK" for r in rows)


def test_ingest_refuses_to_store_a_failed_sanity_check(fake_db, monkeypatch, tmp_path):
    monkeypatch.setattr(ingest, "ROOT", tmp_path)
    monkeypatch.setattr(ingest, "save_and_load", lambda url, path, **kw: b"<html>Access denied</html>")
    stored = []
    monkeypatch.setattr(ingest, "store_chunks", lambda c: stored.append(c) or (0, 0))
    assert ingest.ingest_uk(2006, "ukpga", 46, "Companies Act 2006", "director") == 0 and stored == []


def test_save_and_load_falls_back_to_local_file(tmp_path, monkeypatch):
    p = tmp_path / "x.xml"; p.write_bytes(b"saved by hand")
    monkeypatch.setattr(common, "http_get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("blocked")))
    assert common.save_and_load("https://example.com/x", p) == b"saved by hand"
    assert common.save_and_load("https://example.com/x", tmp_path / "missing.xml") is None


def test_ingest_eu_uses_local_file_when_present(fake_db, monkeypatch, tmp_path):
    (tmp_path / "corpus/statutes/EU").mkdir(parents=True)
    html = EU_PLAIN.replace("</body>", "<p>" + "filler text for length. " * 300 + "</p></body>")
    (tmp_path / "corpus/statutes/EU/General_Data_Protection_Regulation.html").write_text(html)
    monkeypatch.setattr(ingest, "ROOT", tmp_path)
    monkeypatch.setattr(ingest, "fetch_eu", lambda c: pytest.fail("must not hit the network"))
    monkeypatch.setattr(ingest, "store_chunks", lambda chunks: common.store_chunks(chunks, db=fake_db, embed=lambda t: np.zeros((len(t), 384))))
    assert ingest.ingest_eu("32016R0679", "General Data Protection Regulation", 2016, "Article 1") > 0
    assert {"Article 1", "Article 2"} <= {r["section"] for r in fake_db.store["statute_chunks"]}


def test_cli_rejects_unknown_target(capsys):
    assert ingest.main(["mars"]) == 2


# ── US (GovInfo) ────────────────────────────────────────────────────────────
class _Resp:
    def __init__(self, code=200, js=None, text=""): self.status_code, self._js, self.text = code, js, text
    def json(self): return self._js


def test_us_ingest_stores_full_part_text(fake_db, monkeypatch):
    part_html = "<html><body><pre>§ 1.1 Purpose. " + "The Commission shall enforce the rules. " * 80 + "</pre></body></html>"
    calls = []
    def fake_get(path, **params):
        calls.append(path)
        if path.endswith("/summary"):
            return _Resp(200 if "vol1" in path else 404)
        if path.endswith("/granules"):
            return _Resp(200, {"granules": [{"granuleId": "CFR-2024-title16-vol1-part1", "title": "PART 1—GENERAL PROCEDURES"}],
                               "offsetMark": "x", "nextPage": None})
        return _Resp(200, text=part_html)
    monkeypatch.setattr(ingest_us, "_get", fake_get)
    monkeypatch.setattr(ingest_us.time, "sleep", lambda s: None)
    monkeypatch.setenv("GOVINFO_API_KEY", "k")
    monkeypatch.setattr(ingest_us, "store_chunks", lambda chunks: common.store_chunks(chunks, db=fake_db, embed=lambda t: np.zeros((len(t), 384))))
    n = ingest_us.ingest_title("16")
    rows = fake_db.store["statute_chunks"]
    assert n == len(rows) > 0
    assert all(r["jurisdiction"] == "US" and "Commission shall enforce" in r["content"] for r in rows)   # real text, not a title
    assert rows[0]["section"] == "§ 1.1"


def test_us_ingest_reports_missing_edition(monkeypatch, capsys):
    monkeypatch.setattr(ingest_us, "_get", lambda path, **p: _Resp(404))
    assert ingest_us.ingest_title("16") == 0
    assert "CFR_YEAR" in capsys.readouterr().out
