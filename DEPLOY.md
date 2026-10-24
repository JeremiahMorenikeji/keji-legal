# KEJI Legal — Run, Test & Deploy (beginner guide)

Follow the parts **in order**. Every part ends with a **✅ You're done when…** check.
Don't move on until the check passes. Commands are for a terminal opened **inside the
`keji-legal` folder**.

---

## Part 0 — What you need

| Service | Needed for | Cost |
|---|---|---|
| [Supabase](https://supabase.com) | the database | free tier |
| [DeepSeek](https://platform.deepseek.com) **or** [Anthropic](https://console.anthropic.com) | the LLM | pay per use |
| [GitHub](https://github.com) | holds your code | free |
| [Railway](https://railway.app) | runs the API | ~$5/month |
| [Hugging Face](https://huggingface.co) | runs the Streamlit site | free |
| [GovInfo](https://www.govinfo.gov/api-signup) | US law (optional, free) | free |

Python **3.11 or 3.12** (not 3.13 — PyTorch 2.4 doesn't support it). Check: `python --version`.

---

## Part 1 — Install on your laptop

```bash
python -m venv venv
source venv/bin/activate          # Windows:  venv\Scripts\activate
pip install -r requirements-dev.txt
```

First install takes 5–10 minutes (PyTorch is big). On **Linux**, to avoid a ~3 GB download use the
CPU build first:  `pip install torch==2.4.1 --index-url https://download.pytorch.org/whl/cpu`

Then run the offline tests — they need **no keys and no internet**:

```bash
pytest
```

✅ **You're done when:** it ends with `73 passed, 6 skipped`.

---

## Part 2 — Create your `.env` file

```bash
cp .env.example .env              # Windows:  copy .env.example .env
```

Generate **two different** secrets (run this command twice, paste one into each line):

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Fill in `.env`:

| Variable | Where to get it |
|---|---|
| `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY` | Supabase → your project → **Project Settings → API** |
| `DEEPSEEK_API_KEY` (or `ANTHROPIC_API_KEY` + `LLM_PROVIDER=anthropic`) | the provider's dashboard → API keys |
| `KEJI_API_SECRET` | first generated secret |
| `KEJI_REVIEWER_SECRET` | second generated secret (**must be different**) |
| `GOVINFO_API_KEY` | arrives by email after signing up (only needed for US law) |

Leave `KEJI_ENV=development` for now.

> ⚠️ `SUPABASE_SERVICE_KEY` can do **anything** to your database. It lives only in `.env`
> (never committed — `.gitignore` blocks it) and in Railway. **Never** put it in Hugging Face.

✅ **You're done when:** `git status` does **not** list `.env`.

---

## Part 3 — Create the database

1. Supabase dashboard → **SQL Editor → New query**.
2. Open `database/schema.sql`, copy **everything**, paste it in, click **Run**. (Safe to run twice.)
3. Paste and run this to confirm:

```sql
SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY 1;
```

✅ **You're done when** you see `compliance_checks`, `generated_documents`, `matters`, `statute_chunks`.

Then test the connection **from your laptop**:

```bash
python tests/test_db.py
```

✅ **You're done when** you see three ✅ lines, including *"anon key cannot write to statute_chunks"*.
(If you see a SECURITY failure, re-run `schema.sql` — it switches on the protection.)

---

## Part 4 — Test your LLM key

```bash
python -c "from api.llm.provider import get_llm; print(get_llm().complete('Reply with exactly: KEJI OK', [{'role':'user','content':'go'}], max_tokens=10))"
```

✅ **You're done when** it prints something containing `KEJI OK`.

---

## Part 5 — Load the law into the database (ingestion)

The first command downloads the ~25 MB embedding model (one time).

```bash
python corpus/ingest.py uk        # start small: 4 UK Acts, a few minutes
```

Look for `✅ … new chunks stored`. Two things you may see:

* `⛔ SANITY FAIL` — the download wasn't the real document (blocked page, wrong URL). That Act is
  **skipped**, nothing bad is stored. Open the URL printed above it in your browser, save the file
  to the path shown, and re-run — the script uses a file you saved by hand.
* `⚠ Download failed` — usually a network blip. Just re-run; duplicates are skipped automatically.

When UK looks right, do the rest:

```bash
python corpus/ingest.py ca eu
python corpus/ingest_us.py 16 --max-parts 20     # US trial run (needs GOVINFO_API_KEY)
python corpus/ingest_us.py                       # full US run (CFR titles 16 and 17)
```

Watch your database size in Supabase (**Settings → Usage**); the free tier is 500 MB.

✅ **You're done when:** Supabase → **Table Editor → statute_chunks** has rows, and:

```bash
python tests/test_retrieval.py
```

shows `✅ PASS` for each jurisdiction you loaded (`⏭ SKIPPED` = not loaded yet, which is fine).
If one **FAILS**, the numbers tell you where; try ingesting that jurisdiction again, and see
*Troubleshooting* below.

---

## Part 6 — Run everything locally

Open **two terminals** (activate `venv` in both).

```bash
# Terminal 1 — the API
uvicorn api.main:app --reload --port 8000

# Terminal 2 — the website
streamlit run app/main.py
```

Open <http://localhost:8501>. Pick **United Kingdom**, open **Compliance Research** in the left
menu, ask *"What are a director's duties?"*.

Third terminal — automatic end-to-end check:

```bash
python scripts/smoke_test.py
```

✅ **You're done when:** the smoke test ends with `ALL CHECKS PASSED ✅`, and the website shows
cited provisions with a "pending review" label.

---

## Part 7 — Put the code on GitHub

```bash
git add .
git commit -m "KEJI Legal v0.1.0"
git push origin main
```

Check `git status` first: `.env` must **not** appear. GitHub Actions will run the offline tests
automatically (Actions tab).

---

## Part 8 — Deploy the API to Railway

1. <https://railway.app> → **New Project → Deploy from GitHub repo** → pick `keji-legal`.
   Railway reads `railway.toml` and builds `Dockerfile.api` (first build: 5–10 min).
2. Open the service → **Variables** → add **all** of these:

| Variable | Value |
|---|---|
| `KEJI_ENV` | `production` |
| `KEJI_API_SECRET` | same as your `.env` |
| `KEJI_REVIEWER_SECRET` | same as your `.env` |
| `SUPABASE_URL` | from `.env` |
| `SUPABASE_SERVICE_KEY` | from `.env` |
| `LLM_PROVIDER` / `LLM_MODEL` / `DEEPSEEK_API_KEY` (or `ANTHROPIC_API_KEY`) | from `.env` |
| `ALLOWED_ORIGINS` | `https://keji.legal,https://www.keji.legal` |

   Don't set `PORT` — Railway sets it. You don't need `SUPABASE_ANON_KEY` on the API.
3. **Settings → Networking → Generate Domain**. You get something like `keji-api.up.railway.app`.
4. In production the API **refuses to start** if the two secrets are weak or identical — if the
   deploy crashes, read the log; it names the problem.

Test it **from your laptop** against the live API:

```bash
python scripts/smoke_test.py --base https://YOUR-RAILWAY-DOMAIN --approve
```

✅ **You're done when:** it ends with `ALL CHECKS PASSED ✅`. (It also proves a request without
a token gets refused.)

*Memory:* the API loads the embedding model (~600–800 MB RAM). If Railway shows out-of-memory
restarts, raise the service's memory limit.

---

## Part 9 — Deploy the website to Hugging Face Spaces

1. <https://huggingface.co/new-space> → name `keji-legal`, SDK **Streamlit**, visibility **Private**
   for now (see the warning in `README.md`).
2. Push your code to it:

```bash
git remote add hf https://huggingface.co/spaces/YOUR_HF_USERNAME/keji-legal
git push hf main
```

   (Use a Hugging Face **access token** with *write* permission as the password.)
3. Space → **Settings → Variables and secrets → New secret**. Add **only** these two:

| Secret | Value |
|---|---|
| `KEJI_API_BASE_URL` | `https://YOUR-RAILWAY-DOMAIN` (no trailing slash) |
| `KEJI_API_SECRET` | same as the API |

   **Do not** add the Supabase service key or the reviewer secret here. Reviewers type their key
   into the *Review Queue* page themselves.
4. The Space rebuilds. (It installs only `requirements.txt` — Streamlit, requests, dotenv — so it's quick.)

✅ **You're done when:** the Space shows **Running**, the sidebar says `● API · ONLINE`, and a
search returns cited provisions.

---

## Part 10 — Custom domain & release tag

* **API:** Railway → Settings → Networking → **Custom Domain** → `api.keji.legal`; add the CNAME it
  shows at your DNS provider. Then update `KEJI_API_BASE_URL` in the Space to `https://api.keji.legal`.
* **Site:** point `keji.legal` at your Space following Hugging Face's custom-domain docs (or link to the Space).
* **Tag the release:**

```bash
git tag -a v0.1.0 -m "KEJI Legal v0.1.0 — legal research assistant, hybrid RAG, human review"
git push origin v0.1.0
```

✅ **You're done when:** `curl https://api.keji.legal/health` returns `{"status":"ok",...}`.

---

## Using the review step

Every answer is saved as **pending review**. A lawyer opens **Review Queue** in the website,
enters the reviewer key, clicks **Load pending items**, edits the text if needed, then
**Approve** or **Reject**. An item can only be reviewed once.

---

## Troubleshooting

| Symptom | Likely cause → fix |
|---|---|
| `pytest` can't import something | Virtualenv not active (`(venv)` missing in prompt) → activate it |
| `python tests/test_db.py` → permission/`relation does not exist` | `schema.sql` not run, or wrong project URL/keys in `.env` |
| `SECURITY: the anon key could write…` | Re-run `database/schema.sql` |
| Ingestion: `⛔ SANITY FAIL` | Real document not downloaded → save it by hand to the printed path, re-run |
| Ingestion: very few chunks for an Act | Source XML shape differs from what the parser expects → send me the first 40 lines of the saved file in `corpus/statutes/…` |
| US ingestion: *No volumes found* | `GOVINFO_API_KEY` missing/limited, or that year's edition isn't published → set `CFR_YEAR=2024` in `.env` |
| `test_retrieval` FAIL | Corpus for that jurisdiction incomplete, or keyword in the golden set doesn't match your data → check the table it prints, adjust `tests/golden/*.json` |
| Smoke test: `NO_RESULTS` | Corpus not loaded for that jurisdiction |
| Website: *API rejected our token* | `KEJI_API_SECRET` differs between Space and Railway |
| Website: *Cannot reach the KEJI API* | Wrong `KEJI_API_BASE_URL`, or the Railway service is down/asleep |
| Railway deploy crashes immediately | Read the log: `Unsafe production configuration` names the weak/missing variable |
| Railway restarts repeatedly | Out of memory → increase the memory limit |
| LLM answer shows *withheld — no verifiable citation* | The model ignored the citation format. Working as designed; try `LLM_PROVIDER=anthropic` for stricter adherence |

## If a key leaks

Rotate it immediately: Supabase (Settings → API → regenerate), DeepSeek/Anthropic (delete + recreate),
and generate fresh `KEJI_API_SECRET` / `KEJI_REVIEWER_SECRET`, then update Railway and the Space.
