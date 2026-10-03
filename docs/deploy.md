# Deploy a free hosted demo (Vercel + Neon)

One Vercel project serves the web app and the API (as a Python function); Neon is the database. Synthetic data only. Why this setup: [decision 0006](decisions/0006-free-hosted-demo.md).

## 1. Neon: create the database
1. Sign up at https://neon.tech → **New project** (any name, region close to you, Postgres 16 or newer).
2. On the project dashboard click **Connect**, leave **Connection pooling** on, and copy the connection string (host contains `-pooler`). Don't paste it into chats or commits.

## 2. Create tables, seed demo data, get the Vercel variables (once, from your PC)
In `lifegrid/backend`:

```powershell
.venv\Scripts\python scripts\seed_remote.py
```

Paste the Neon connection string when asked (hidden). The script makes the keys (saved in `backend/deploy.env`, git-ignored; re-runs reuse them), runs migrations and the seed, and prints every Vercel variable.

## 3. Vercel: import the repo
1. https://vercel.com/new → import the GitHub repo. **Root Directory: leave as the repo root** (`vercel.json` sets the build).
2. **Environment Variables** (add before the first deploy; paste what the script printed):

| Name | Value |
| --- | --- |
| `DATABASE_URL` | pooled Neon URL (`postgresql+psycopg://...-pooler...`) |
| `ENV` | `demo` |
| `CELERY_ALWAYS_EAGER` | `true` |
| `JWT_SECRET`, `PHONE_ENC_KEY`, `PHONE_HASH_KEY`, `TOTP_ENC_KEY` | from the script |
| `APP_ORIGIN` | `https://<project>.vercel.app` (add after the first deploy shows the URL, then redeploy) |

3. **Deploy.** Check `https://<project>.vercel.app/api/v1/docs`.

## Using it
Staff sign in at `/login` (demo accounts in the README); donors and requesters use `/app` (codes shown on screen). The first request after a quiet spell takes a few seconds while the function and Neon wake up.

## If the build fails
- *"exceeds the maximum size"*: the Python bundle is over 500 MB. Tell Claude; the fallback is the API on a container host.
- Function errors: Vercel → project → **Logs**.
