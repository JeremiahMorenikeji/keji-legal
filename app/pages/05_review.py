"""Review queue — for approved reviewers only (needs the reviewer key)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402
from components import shared  # noqa: E402

shared.setup("Review Queue", "✅")
shared.sidebar()

st.title("✅ Review Queue")
st.caption("Every output starts as *pending review*. A qualified reviewer approves or rejects it here.")
doc = shared.document_panel("review")  # e.g. a lawyer's amended text from Word

key = st.text_input("Reviewer key", type="password", key="reviewer_key",
                    help="Given only to people authorised to approve outputs.")
hdr = {"X-Reviewer-Key": key} if key else {}

if st.button("Load pending items"):
    data, err = shared.api_call("GET", "/review/pending", headers=hdr)
    st.session_state["pending"] = {"data": data, "err": err}

pending = st.session_state.get("pending")
if pending:
    if pending["err"]:
        st.error(pending["err"])
    elif not pending["data"]["items"]:
        st.success("Nothing waiting for review. 🎉")
    else:
        st.write(f"**{pending['data']['count']} item(s) pending**")
        for item in pending["data"]["items"]:
            cid = item["id"]
            label = f"{item.get('check_type', 'compliance')} · {item.get('jurisdiction') or '—'} · {item['query'][:70]}"
            with st.expander(label):
                st.markdown("**Query**"); st.text(item["query"])
                edited = st.text_area("Reviewed output (edit if needed)", key=f"out_{cid}", height=220,
                                      value=item.get("validated_output") or item.get("raw_output") or "")
                if doc:
                    st.button("Use the uploaded document as the reviewed output", key=f"usedoc_{cid}",
                              on_click=lambda k=f"out_{cid}", t=doc["text"]: st.session_state.__setitem__(k, t))
                note = st.text_input("Reviewer note", key=f"note_{cid}", max_chars=2000)
                for c in item.get("citations", [])[:8]:
                    st.caption(f"• {c.get('statute_name', '?')} [{c.get('section', '')}]")
                a, r = st.columns(2)
                body = {"validated_output": edited, "reviewer_note": note or None}
                if a.button("Approve", key=f"ok_{cid}", type="primary"):
                    _, e = shared.api_call("PUT", f"/compliance/{cid}/approve", json=body, headers=hdr)
                    st.error(e) if e else st.success("Approved. Click “Load pending items” to refresh.")
                if r.button("Reject", key=f"no_{cid}"):
                    _, e = shared.api_call("PUT", f"/compliance/{cid}/reject", json=body, headers=hdr)
                    st.error(e) if e else st.success("Rejected. Click “Load pending items” to refresh.")
