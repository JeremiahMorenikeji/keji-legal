"""KEJI Legal — dashboard. Run with:  streamlit run app/main.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # lets pages import `components.*`

import streamlit as st  # noqa: E402
from components import shared  # noqa: E402

shared.setup("Dashboard")
code = shared.sidebar()

st.markdown(
    """
<div class="keji-hero">
  <div class="keji-mark">K <span>⚖</span> G</div>
  <div class="keji-name">KEJI LEGAL · RESEARCH ASSISTANT</div>
  <div class="keji-tag">The law, wherever you are.</div>
</div>""",
    unsafe_allow_html=True,  # static content only
)

c1, c2, c3 = st.columns(3)
c1.metric("Active Jurisdiction", f"{shared.FLAGS[code]} {code}")
c2.metric("API Status", "Live" if shared._api_online(shared.API_BASE) else "Offline")
c3.metric("Build", "v0.1.0")
st.divider()
shared.document_panel("home")  # upload once; every page can use it

st.markdown("### Workflows")
st.markdown(
    "- **Compliance Research** — ask a question; get cited statutory provisions.\n"
    "- **Contract Review** — paste a clause; get triage flags plus related statutes.\n"
    "- **Review Queue** — for approved reviewers: approve or reject pending outputs."
)
st.info("Pick a workflow from the sidebar menu to begin.")
st.caption(shared.DISCLAIMER)
