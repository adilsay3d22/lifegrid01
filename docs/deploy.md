# Deploy a free hosted demo (Vercel + Neon)

One Vercel project serves the web app and the API (as a Python function); Neon is the database. Synthetic data only. Why this setup: [decision 0006](decisions/0006-free-hosted-demo.md).

## 1. Neon: create the database
1. Sign up at https://neon.tech → **New project** (any name, region close to you, Postgres 16 or newer).
2. On the project dashboard click **Connect**. Copy two connection strings:
   - **Pooled** (host contains `-pooler`) → for Vercel.
   - **Direct** (toggle "Connection pooling" off) → for migrations and the seed.
3. In both, change the start `postgresql://` to `postgresql+psycopg://`. Keep `?sslmode=require`.

## 2. Make three keys
Run three times and save the outputs as PHONE_ENC_KEY, PHONE_HASH_KEY, TOTP_ENC_KEY. Run once more for JWT_SECRET.

```bash
python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"
```

## 3. Create tables and seed demo data (once, from your PC)
PowerShell, in `lifegrid\backend` (use the **direct** URL and the same keys you give Vercel):

```powershell
$env:DATABASE_URL="postgresql+psycopg://...direct...neon.tech/neondb?sslmode=require"
$env:ENV="demo"; $env:JWT_SECRET="seed-only"
$env:PHONE_ENC_KEY="..."; $env:PHONE_HASH_KEY="..."; $env:TOTP_ENC_KEY="..."
.venv\Scripts\alembic upgrade head
.venv\Scripts\python -m simulation seed
```

## 4. Vercel: import the repo
1. https://vercel.com/new → import the GitHub repo. **Root Directory: leave as the repo root** (`vercel.json` sets the build).
2. **Environment Variables** (add before the first deploy):

| Name | Value |
| --- | --- |
| `DATABASE_URL` | pooled Neon URL (`postgresql+psycopg://...-pooler...`) |
| `ENV` | `demo` |
| `CELERY_ALWAYS_EAGER` | `true` |
| `JWT_SECRET` | your 4th key |
| `PHONE_ENC_KEY`, `PHONE_HASH_KEY`, `TOTP_ENC_KEY` | same as step 3 |
| `APP_ORIGIN` | `https://<project>.vercel.app` (add after the first deploy shows the URL, then redeploy) |

3. **Deploy.** Check `https://<project>.vercel.app/api/v1/docs`.

## Using it
Staff sign in at `/login` (demo accounts in the README); donors and requesters use `/app` (codes shown on screen). The first request after a quiet spell takes a few seconds while the function and Neon wake up.

## If the build fails
- *"exceeds the maximum size"*: the Python bundle is over 500 MB. Tell Claude; the fallback is the API on a container host.
- Function errors: Vercel → project → **Logs**.
