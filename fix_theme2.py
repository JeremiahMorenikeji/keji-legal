# fix_theme2.py - high-contrast, bold, easy-to-read theme on every page. Safe to run twice.
from pathlib import Path
import re
import sys

if not Path("app/components/shared.py").exists() or not Path("app/pages/02_compliance.py").exists():
    sys.exit("Run this from inside the keji-legal folder.")

CONFIG = """# High-contrast light theme (the page CSS in app/components/shared.py also forces these colours).
[theme]
base = "light"
primaryColor = "#1A1A1A"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#EFE8D4"
textColor = "#000000"
font = "sans serif"

[server]
maxUploadSize = 10

[browser]
gatherUsageStats = false
"""

CSS = '''_CSS = """<style>
html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stHeader"],[data-testid="stMain"]{background:#FFFFFF!important}
section[data-testid="stSidebar"],section[data-testid="stSidebar"]>div{background:#EFE8D4!important}
html,body,.stApp,.stMarkdown,.stMarkdown p,.stMarkdown li,.stMarkdown span,.stText,label,p,li,
[data-testid="stWidgetLabel"] p,[data-testid="stMetricLabel"],[data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] p,
[data-testid="stAlert"] p,[data-testid="stAlert"] div,[data-testid="stExpander"] summary p,[data-testid="stExpander"] summary span,
[data-testid="stExpanderDetails"] p,[data-testid="stFileUploaderDropzone"] span,[data-testid="stFileUploaderDropzone"] small,
[data-testid="stFileUploaderFile"] span,[data-testid="stFileUploaderFile"] small,
textarea,input,[data-baseweb="select"] div,[data-baseweb="select"] span{color:#000!important;font-weight:700!important}
.stMarkdown p,.stMarkdown li,.stText,label,[data-testid="stAlert"] p{font-size:1.08rem!important;line-height:1.65!important}
[data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] p{color:#222!important;font-size:.98rem!important}
h1,h2,h3,h4,h5,h1 span,h2 span,h3 span{color:#4A3500!important;font-weight:800!important}
textarea,input,[data-baseweb="select"]>div{background:#FFF!important;border:2px solid #000!important;border-radius:6px!important;font-size:1.05rem!important}
textarea::placeholder,input::placeholder{color:#444!important;opacity:1!important;font-weight:600!important}
[data-baseweb="popover"],[data-baseweb="popover"] ul,ul[role="listbox"] li{background:#FFF!important;color:#000!important;font-weight:700!important}
.stButton>button,[data-testid="stFileUploaderDropzone"] button,button[kind="primary"],button[kind="secondary"]{background:#1A1A1A!important;border:2px solid #000!important;border-radius:6px!important}
.stButton>button *,[data-testid="stFileUploaderDropzone"] button *,button[kind="primary"] *,button[kind="secondary"] *{color:#FFF!important;font-weight:800!important;font-size:1.05rem!important}
.stButton>button:hover,[data-testid="stFileUploaderDropzone"] button:hover,button[kind="primary"]:hover,button[kind="secondary"]:hover{background:#E3BC47!important}
.stButton>button:hover *,[data-testid="stFileUploaderDropzone"] button:hover *,button[kind="primary"]:hover *,button[kind="secondary"]:hover *{color:#000!important}
[data-testid="stFileUploaderDropzone"]{background:#FFFDF0!important;border:2px dashed #000!important;border-radius:8px!important}
[data-testid="stExpander"]{border:2px solid #000!important;border-radius:6px!important;background:#FFF!important}
.stText,[data-testid="stText"]{color:#000!important;white-space:pre-wrap!important}
[data-testid="stMetricValue"],[data-testid="stMetricValue"] div{color:#000!important;font-weight:800!important}
.keji-result{background:#FFFDF0;border:2px solid #000;border-radius:8px;padding:16px 18px;color:#000;font-weight:700;font-size:1.08rem;line-height:1.7;word-wrap:break-word}
.keji-hero{text-align:center;padding:18px 0 10px;border-bottom:3px solid #000;margin-bottom:18px}
.keji-mark{font-size:48px;font-weight:900;letter-spacing:.15em;color:#000}
.keji-mark span{color:#6B5200}
.keji-name{font-size:15px;font-weight:800;letter-spacing:.3em;color:#4A3500}
.keji-tag{font-size:17px;font-weight:700;font-style:italic;color:#222;margin-top:4px}
</style>"""'''

TEST = '''from pathlib import Path

from app.components import shared


def test_theme_is_light_and_high_contrast():
    cfg = (Path(__file__).resolve().parent.parent / ".streamlit" / "config.toml").read_text()
    assert 'base = "light"' in cfg and 'textColor = "#000000"' in cfg and "maxUploadSize" in cfg
    assert "font-weight:700" in shared._CSS and "keji-result" in shared._CSS
    assert "#E2E2E2" not in shared._CSS and "#080809" not in shared._CSS     # the old dark colours are gone
'''

changes, problems, done = {}, [], []


def cur(rel):
    return changes.get(rel, Path(rel).read_text(encoding="utf-8"))


def edit(rel, fn, marker):
    s = cur(rel)
    if marker in s:
        done.append(f"{rel} ({marker})")
        return
    new = fn(s)
    if new is None or new == s:
        problems.append(f"{rel}: could not find the text to change ({marker})")
        return
    changes[rel] = new


def swap(old, new):
    return lambda s: s.replace(old, new, 1) if old in s else None


def regex_swap(pattern, replacement):
    def f(s):
        m = re.search(pattern, s, re.S)
        return s[:m.start()] + replacement + s[m.end():] if m else None
    return f


# shared.py: the stylesheet and readable status colours
edit("app/components/shared.py", regex_swap(r'_CSS = """<style>.*?</style>"""', CSS), "keji-result")
edit("app/components/shared.py", swap('("#6AB187", "ONLINE")', '("#05521F", "ONLINE")'), '"#05521F"')
edit("app/components/shared.py", swap('("#C0614A", "OFFLINE")', '("#8E0017", "OFFLINE")'), '"#8E0017"')
edit("app/components/shared.py", swap("font-size:10px;color:{colour};font-family:monospace",
                                      "font-size:14px;font-weight:800;color:{colour};font-family:monospace"), "font-size:14px;font-weight:800")

# main.py: the banner uses CSS classes instead of dark-theme colours
HERO = ('<div class="keji-hero">\n  <div class="keji-mark">K <span>\u2696</span> G</div>\n'
        '  <div class="keji-name">KEJI LEGAL \u00b7 RESEARCH ASSISTANT</div>\n'
        '  <div class="keji-tag">The law, wherever you are.</div>\n</div>')
edit("app/main.py", regex_swap(r"<div style='text-align:center;padding:20px 0 12px'>.*?</div><hr style='[^']*'>", HERO), 'class="keji-hero"')

# compliance page: the result is normal readable text in a bordered box (not a greyed-out disabled field)
OLD_RESULT = ('        st.markdown("### Result")\n'
              '        st.text_area("Agent output (pending human review)", value=data.get("validated_output") or "",\n'
              '                     height=300, disabled=True)  # text_area: nothing in here can inject HTML\n')
NEW_RESULT = ('        st.markdown("### Result (pending human review)")\n'
              '        import html as _html  # the text is escaped first, so model output can never inject markup\n'
              '        _out = _html.escape(data.get("validated_output") or "No output.").replace("\\n", "<br>")\n'
              '        st.markdown(f\'<div class="keji-result">{_out}</div>\', unsafe_allow_html=True)\n')
edit("app/pages/02_compliance.py", swap(OLD_RESULT, NEW_RESULT), 'class="keji-result"')

# the test that looked for the old disabled box
OLD_T = ('    out = [t for t in at.text_area if t.label.startswith("Agent output")][0]\n'
         '    assert "Companies Act 2006" in out.value and out.disabled\n')
NEW_T = ('    assert any("Companies Act 2006" in m.value for m in at.markdown)       # result is normal, readable page text\n'
         '    assert not [t for t in at.text_area if t.label.startswith("Agent output")]   # no greyed-out disabled box\n')
if Path("tests/test_frontend.py").exists():
    edit("tests/test_frontend.py", swap(OLD_T, NEW_T), "no greyed-out disabled box")

if problems:
    print("Nothing was changed, because:")
    for p in problems:
        print("  !!", p)
    print("Send me these lines.")
    sys.exit(1)

for rel, text in changes.items():
    Path(rel + ".bak7").write_text(Path(rel).read_text(encoding="utf-8"), encoding="utf-8")
    Path(rel).write_text(text, encoding="utf-8")
    print(f"  patched: {rel}")
for rel in done:
    print(f"  already up to date: {rel}")


def put(rel, text):
    p = Path(rel)
    if p.exists() and p.read_text(encoding="utf-8") == text:
        print(f"  already up to date: {rel}")
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        Path(rel + ".bak7").write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    p.write_text(text, encoding="utf-8")
    print(f"  wrote: {rel}")


put(".streamlit/config.toml", CONFIG)
put("tests/test_theme.py", TEST)
print("\nDone. Restart Streamlit (Ctrl+C, then: streamlit run app/main.py) and press Ctrl+F5 in the browser.")
