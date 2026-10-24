---
title: KEJI Legal
emoji: ⚖
colorFrom: gray
colorTo: yellow
sdk: streamlit
sdk_version: 1.38.0
python_version: "3.11"
app_file: app/main.py
pinned: false
license: mit
---

# KEJI Legal — *The law, wherever you are.*

A legal **research assistant** for US, Canadian, UK and EU law. It retrieves statutory
provisions and cites them. **It does not give legal advice.** Every output is stored as
`pending_review` until a qualified person approves it.

> **This is a research tool. All outputs require review by a qualified legal professional.**

## How it works

```
 Streamlit UI (app/)  ──HTTPS + bearer token──►  FastAPI (api/)  ──►  Supabase Postgres
  Hugging Face Space                              Railway             pgvector + full-text
                                                     │
                       ┌─────────────────────────────┤
                       ▼                             ▼
          Hybrid retrieval (dense + lexical,    LLM (DeepSeek or Claude)
          fused with RRF, jurisdiction-filtered)  cites ONLY retrieved text
                       │
                       ▼
          Citation validator: unknown chunk IDs stripped, quotes checked,
          uncited answers withheld  →  saved as pending_review  →  human approves
```

| Folder | What lives there |
|---|---|
| `api/` | FastAPI app, agents (router + ReAct compliance agent), RAG engine, LLM providers |
| `app/` | Streamlit dashboard + pages (Compliance, Contracts, Review Queue) |
| `corpus/` | Ingestion scripts for UK / CA / EU / US legislation |
| `database/schema.sql` | The whole database, run once in Supabase |
| `tests/` | 73 offline tests + live tests (`KEJI_LIVE=1`) + golden retrieval sets |
| `scripts/smoke_test.py` | End-to-end check of a running API (local or deployed) |

## Quick start

**Full step-by-step instructions for beginners: [`DEPLOY.md`](DEPLOY.md).**

```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                 # then fill it in
pytest                                               # 73 passed, 6 skipped — no keys needed
```

## Before you make the Space public

The Space holds the API secret on its server, so **anyone who can open the Space can run queries
that use your LLM credits.** Keep the Space private while testing, and add a login or rate
limit before announcing it publicly.

## Not legal advice

KEJI Legal is not a law firm and does not provide legal advice. Statute text may be out of date
or incompletely ingested. Always verify against the official source.
