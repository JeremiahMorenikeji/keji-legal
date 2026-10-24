"""Shared Streamlit helpers: theme, jurisdiction sidebar, API client."""
import os

import requests
import streamlit as st
from dotenv import load_dotenv

from .documents import ALLOWED_TYPES, MAX_UPLOAD_MB, ingest_upload

load_dotenv()

API_BASE = os.getenv("KEJI_API_BASE_URL", "http://localhost:8000").rstrip("/")

JURISDICTIONS = {
    "🇺🇸 United States (US)": "US",
    "🇨🇦 Canada (CA)": "CA",
    "🇬🇧 United Kingdom (UK)": "UK",
    "🇪🇺 European Union (EU)": "EU",
}
FLAGS = {"US": "🇺🇸", "CA": "🇨🇦", "UK": "🇬🇧", "EU": "🇪🇺"}

DISCLAIMER = (
    "KEJI Legal is a research assistant, not a law firm. Outputs retrieve and cite statutes only, "
    "are pending review, and must be checked by a qualified legal professional before any action is taken."
)

_CSS = """<style>
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
</style>"""


def setup(title: str, icon: str = "⚖") -> None:
    """Call FIRST on every page (Streamlit requires set_page_config before anything else)."""
    st.set_page_config(page_title=f"{title} — KEJI Legal", page_icon=icon, layout="wide",
                       initial_sidebar_state="expanded")
    st.markdown(_CSS, unsafe_allow_html=True)  # static string only — never user content


def api_headers(extra: dict | None = None) -> dict:
    """The API secret lives on the Streamlit SERVER (env var), so it never reaches the browser."""
    h = {"Content-Type": "application/json"}
    secret = os.getenv("KEJI_API_SECRET")
    if secret:
        h["Authorization"] = f"Bearer {secret}"
    return {**h, **(extra or {})}


def api_call(method: str, path: str, *, json: dict | None = None, headers: dict | None = None,
             timeout: int = 90) -> tuple[dict | None, str | None]:
    """Returns (data, error_message). Exactly one of them is None."""
    try:
        r = requests.request(method, f"{API_BASE}{path}", json=json, headers=api_headers(headers), timeout=timeout)
    except requests.exceptions.ConnectionError:
        return None, (f"Cannot reach the KEJI API at {API_BASE}. Locally: run "
                      "`uvicorn api.main:app --reload --port 8000`. In production: set KEJI_API_BASE_URL "
                      "to your Railway API address.")
    except requests.exceptions.Timeout:
        return None, "The API took too long to respond. Please try again."
    if r.status_code == 200:
        return r.json(), None
    if r.status_code == 401:
        return None, "The API rejected our token. KEJI_API_SECRET here must match the API's KEJI_API_SECRET."
    if r.status_code == 403:
        return None, "Access denied — check the reviewer key."
    if r.status_code == 409:
        return None, "That item was already reviewed."
    if r.status_code == 422:
        return None, "The request was not valid (check the length and fields of your input)."
    if r.status_code == 503:
        return None, "The research service is temporarily unavailable. Please try again shortly."
    return None, f"API error {r.status_code}."


@st.cache_data(ttl=20, show_spinner=False)
def _api_online(base: str) -> bool:
    try:
        return requests.get(f"{base}/health", timeout=3).status_code == 200
    except Exception:  # noqa: BLE001
        return False


def sidebar() -> str:
    """Renders the jurisdiction picker + API status on EVERY page; returns 'US' | 'CA' | 'UK' | 'EU'."""
    with st.sidebar:
        st.markdown("## ⚖ KEJI Legal")
        label = st.selectbox("Jurisdiction", list(JURISDICTIONS), key="jurisdiction_label")
        online = _api_online(API_BASE)
        colour, text = ("#05521F", "ONLINE") if online else ("#8E0017", "OFFLINE")
        st.markdown(f'<div style="font-size:14px;font-weight:800;color:{colour};font-family:monospace">● API · {text}</div>',
                    unsafe_allow_html=True)
        st.caption("Your selection always overrides any automatic suggestion.")
    code = JURISDICTIONS[label]
    st.session_state["jurisdiction"] = code
    return code


def document_panel(where: str):
    """
    Upload box shown on EVERY page. The extracted text is kept in st.session_state["doc"], so a document
    uploaded on one page is available on all of them. Returns the current document (a dict) or None.
    """
    n = st.session_state.get("doc_uploader_n", 0)
    with st.container(border=True):
        st.markdown("#### \U0001F4CE Attach a document (optional)")
        up = st.file_uploader(
            "Upload a PDF, Word (.docx) or text (.txt, .md) file", type=ALLOWED_TYPES, key=f"doc_uploader_{n}",
            help=f"Up to {MAX_UPLOAD_MB} MB. Scanned (image-only) PDFs are not supported.")
        if up is not None:
            doc, err = ingest_upload(up.name, up.getvalue(), st.session_state.get("doc"))
            if err:
                st.error(err)
            elif doc:
                st.session_state["doc"] = doc
        doc = st.session_state.get("doc")
        if doc:
            st.success(f"Using: **{doc['name']}** - {len(doc['text']):,} characters")
            for w in doc.get("warnings", []):
                st.warning(w)
            with st.expander("Preview the text that was extracted"):
                st.text(doc["text"][:3000])
            if st.button("Remove document", key=f"doc_remove_{where}"):
                st.session_state.pop("doc", None)
                st.session_state["doc_uploader_n"] = n + 1   # a new, empty uploader
                st.rerun()
        st.caption("Privacy: the text of an attached document is sent to the AI provider so it can understand your "
                   "question. Do not attach confidential client documents unless your provider's terms allow it. "
                   "Only the file name and size are saved in the database - never the text.")
    return doc
