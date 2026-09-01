# Deploying EMAI Scheduler

Three paths, in increasing order of effort. All of them need the same four
decisions: where Postgres lives, what `SECRET_KEY` is, what URL the API is
reachable at, and what URL the app is reachable at.

---

## 1. Try it locally (5 minutes)

```bash
cp .env.example .env
# put a real value in SECRET_KEY:
python3 -c "import secrets; print(secrets.token_urlsafe(48))"

docker compose up --build
docker compose run --rm api python -m app.seed    # optional demo data
```

- App: http://localhost:5173
- API docs: http://localhost:8000/docs
- Demo logins (after seeding): `admin@demo-em.example.com` / `demo1234`,
  and three physician accounts printed by the seed command.

Without Docker, use `make setup` then `make seed`, `make dev-api`, `make dev-web`.

---

## 2. One small server (a $10-20/mo VPS)

Enough for the first several customers -- a 40-physician group generates
trivial load; the solver is the only heavy thing and it runs for seconds at
a time.

1. Point two DNS records at the box, e.g. `app.yourdomain.com` and
   `api.yourdomain.com`.
2. Clone the repo, write `.env`:

   ```bash
   SECRET_KEY=<generated>
   ENVIRONMENT=production
   PUBLIC_BASE_URL=https://api.yourdomain.com
   FRONTEND_BASE_URL=https://app.yourdomain.com
   CORS_ORIGINS=["https://app.yourdomain.com"]
   POSTGRES_PASSWORD=<something long>
   ```

3. `docker compose up -d --build`
4. Put a TLS terminator in front (Caddy is the least work):

   ```
   api.yourdomain.com {
       reverse_proxy localhost:8000
   }
   app.yourdomain.com {
       reverse_proxy localhost:5173
   }
   ```

5. Back up the database on a schedule. This is the one thing you cannot skip:

   ```bash
   docker compose exec -T db pg_dump -U emai emai_scheduler | gzip > backup-$(date +%F).sql.gz
   ```

### Upgrades

```bash
git pull && docker compose up -d --build
```

Migrations run automatically on API start (`alembic upgrade head`).

---

## 3. Managed platforms (Railway / Render / Fly.io)

The two services deploy independently:

**API** -- deploy `backend/` as a Docker service.
- Start command: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Attach a managed Postgres and set `DATABASE_URL`
  (`postgresql+psycopg2://...` -- if the platform hands you a `postgres://`
  URL, rewrite the scheme).
- Health check path: `/health/ready`
- Set `SECRET_KEY`, `PUBLIC_BASE_URL`, `FRONTEND_BASE_URL`, `CORS_ORIGINS`.

**Frontend** -- deploy `frontend/` as a static site.
- Build: `npm ci && npm run build`, publish directory `dist`
- Build-time env: `VITE_API_BASE_URL` (and the OAuth client ids if used).
  These are compiled into the bundle, so changing them requires a rebuild.
- The host must rewrite unknown paths to `/index.html` (it's a single-page
  app). `frontend/nginx.conf` does this if you deploy the container instead.

---

## Configuration reference

Everything is environment variables; see `.env.example` for the full list.

| Variable | Required | Notes |
| --- | --- | --- |
| `SECRET_KEY` | yes | Signs JWTs. Rotating it signs everyone out. |
| `DATABASE_URL` | yes in prod | Defaults to a local SQLite file, which is fine for a trial and nothing else. |
| `PUBLIC_BASE_URL` | yes | Where the API is reachable; used in calendar-feed URLs. |
| `FRONTEND_BASE_URL` | yes | Where the app is reachable; used in invite/reset email links. |
| `CORS_ORIGINS` | yes | JSON array. Set it to your app origin in production rather than leaving it open. |
| `ANTHROPIC_API_KEY` | no | Enables natural-language request parsing and AI schedule summaries. Without it both fall back to deterministic versions. |
| `GOOGLE_CLIENT_ID` / `MICROSOFT_CLIENT_ID` | no | Enables the matching sign-in button. Must match the frontend build arg. |
| `SMTP_*`, `EMAIL_FROM_ADDRESS` | no | Without SMTP, invite/reset emails are logged and the invite link is shown in the UI instead. |
| `RATE_LIMIT_ENABLED` | no | Defaults on. |
| `LOG_LEVEL` | no | `INFO` by default. |

---

## Before you take real customer data

These are deliberately listed rather than pretended away.

- **Set `CORS_ORIGINS` to your actual origin.** The default (`*`) is a dev
  convenience.
- **Back up Postgres**, and test a restore at least once.
- **Configure SMTP**, or invites and password resets only work by copying
  links out of the UI by hand.
- **Rate limiting is per-process.** Running more than one API worker/replica
  means the effective limit multiplies; move it to Redis if you scale out.
- **Shift times are stored without timezone conversion.** Each site has a
  timezone field, but shift instances are built from naive local times. A
  single-timezone customer is unaffected; a customer spanning timezones needs
  this addressed first.
- **HIPAA/BAA.** This system stores physician names, emails, credentials and
  schedules -- staffing data, not patient data (no PHI), which is why it
  isn't structured as a HIPAA system today. Confirm that boundary before
  selling into a hospital, because any feature that touches patient volumes
  or case data changes the answer.
- **No per-tenant encryption or data residency controls**, which larger
  hospital systems will ask about during procurement.
