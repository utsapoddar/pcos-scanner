# PCOS Food Scanner (Python prototype)

Streamlit prototype: scan a barcode → get a PCOS-aware score (1–10) + serving advice + save/remove. Validates scoring logic before any mobile port.

## Setup

```bash
cd ~/projects/pcos-scanner
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in NVIDIA_API_KEY
streamlit run app.py
```

## Layout

- `app.py` — Streamlit UI (Scan / Saved / Profile tabs)
- `core/openfoodfacts.py` — barcode → nutriments via Open Food Facts
- `core/scoring.py` — deterministic rule-based score
- `core/personalize.py` — NVIDIA OpenAI-compatible endpoint (`https://integrate.api.nvidia.com/v1`) adjusts score + writes explanation against user profile
- `core/profile.py` — load/save PCOS profile (4-type + symptom flags)
- `core/db.py` — Supabase CRUD for profile + saved foods + personalization cache
- `migrations/` — SQL migrations auto-run on app startup

## Deploy to Streamlit Cloud

Push this repo to GitHub.
Go to https://share.streamlit.io and create a new app.
Point the app at `app.py`.
Add `NVIDIA_API_KEY` in Streamlit Secrets.
Click Deploy.

### Supabase setup

1. Create a Supabase project at https://supabase.com.
2. Copy the Project URL and anon key from Settings → API.
3. Copy the Postgres URI from Settings → Database → Connection String → URI mode (transaction pooler).
4. Add these to Streamlit Cloud Secrets:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_DB_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`

On first deploy, Supabase will auto-run migrations on startup. To add a schema change later, drop a new file like `migrations/002_add_column.sql` and push — it runs automatically on the next redeploy.

See `~/.claude/plans/can-we-make-this-proud-quilt.md` for full spec.
