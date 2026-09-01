# Deploying EMAI Scheduler

The app ships as **one container** that serves both the API and the web UI
from the same origin. That means one service to deploy, one URL, no CORS to
configure, and nothing about your API address baked into the frontend bundle.

You need exactly two decisions to go live: where Postgres lives, and what
`SECRET_KEY` is.

---

## Run it locally (5 minutes)

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # paste into SECRET_KEY

docker compose up --build
docker compose exec app python -m app.seed    # optional demo data
```

Open **http://localhost:8000**. After seeding, sign in as
`admin@demo-em.example.com` / `demo1234`; the seed prints physician logins
too, so you can see the self-service side.

Without Docker: `make setup`, `make seed`, then `make dev-api` and
`make dev-web` (the dev server runs on :5173 and talks to the API on :8000).

To run the *production* shape locally — one process, one port — build the
frontend first and the API will serve it:

```bash
make build          # writes frontend/dist
make dev-api        # http://localhost:8000 now serves the app too
```

---

## Host it (today)

### Render

The repo has a `render.yaml`. Create a Blueprint from your fork; it provisions
the web service and a managed Postgres, generates `SECRET_KEY`, and points
`PUBLIC_BASE_URL` at the service's own URL. Nothing else is required.

Seed demo data afterwards from the service's Shell tab: `python -m app.seed`.

### Fly.io

```bash
fly launch --no-deploy --copy-config
fly postgres create --name emai-scheduler-db
fly postgres attach emai-scheduler-db
fly secrets set SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
fly secrets set PUBLIC_BASE_URL=https://<your-app>.fly.dev
fly deploy
fly ssh console -C "python -m app.seed"     # optional demo data
```

### Any Docker host (Railway, Fly, ECS, a VPS)

```bash
docker build -t emai-scheduler .
docker run -p 8000:8000 \
  -e SECRET_KEY=... \
  -e DATABASE_URL=postgres://user:pass@host:5432/db \
  -e PUBLIC_BASE_URL=https://sched.your-domain.com \
  emai-scheduler
```

`postgres://` and `postgresql://` URLs are both accepted — the app rewrites
them to the driver SQLAlchemy needs, so a database attached by Render, Fly or
Heroku works as-is.

### A plain VPS with compose

Point DNS at the box, set `PUBLIC_BASE_URL=https://sched.your-domain.com` in
`.env`, `docker compose up -d --build`, and put a TLS terminator in front:

```
sched.your-domain.com {
    reverse_proxy localhost:8000
}
```

Then back up the database on a schedule. This is the one thing you cannot
skip:

```bash
docker compose exec -T db pg_dump -U emai emai_scheduler | gzip > backup-$(date +%F).sql.gz
```

Upgrades are `git pull && docker compose up -d --build`; migrations run
automatically on start.

---

## Hosting the frontend separately (optional)

If you'd rather put the UI on a CDN, build it with `VITE_API_BASE_URL` set to
your API origin and deploy `frontend/dist` as a static site (it needs an
SPA rewrite to `/index.html`; `frontend/Dockerfile` + `frontend/nginx.conf`
do this if you want it as a container). Then on the API set:

- `CORS_ORIGINS=["https://app.your-domain.com"]`
- `FRONTEND_BASE_URL=https://app.your-domain.com` (so invite and password
  reset emails link to the UI rather than the API)

---

## Configuration reference

Everything is environment variables; `.env.example` has the full list.

| Variable | Required | Notes |
| --- | --- | --- |
| `SECRET_KEY` | yes | Signs JWTs. Rotating it signs everyone out. |
| `DATABASE_URL` | yes in prod | Defaults to a local SQLite file, which is fine for a trial and nothing else. `postgres://` URLs are rewritten automatically. |
| `PUBLIC_BASE_URL` | yes | The origin users reach. Used for calendar-feed URLs and invite/reset email links. |
| `CORS_ORIGINS` | no | Leave `[]` for the single-container setup. Only needed when the UI is on another origin. |
| `FRONTEND_BASE_URL` | no | Only when hosting the UI separately; defaults to `PUBLIC_BASE_URL`. |
| `STATIC_DIR` | no | Where the built frontend lives. The image sets this; locally it auto-detects `frontend/dist`. Unset with no build present = API only. |
| `ANTHROPIC_API_KEY` | no | Enables natural-language request parsing and AI schedule summaries; both fall back to deterministic versions without it. |
| `GOOGLE_CLIENT_ID` / `MICROSOFT_CLIENT_ID` | no | Enables the matching sign-in button. |
| `SMTP_*`, `EMAIL_FROM_ADDRESS` | no | Without SMTP, invite/reset emails are logged and the invite link is shown in the UI instead. |
| `RATE_LIMIT_ENABLED` | no | Defaults on. |
| `LOG_LEVEL` | no | `INFO` by default. |

---

## Before you take real customer data

Listed rather than pretended away.

- **Back up Postgres**, and test a restore at least once.
- **Configure SMTP**, or invites and password resets only work by copying
  links out of the UI by hand.
- **Rate limiting is per-process.** More than one worker or replica multiplies
  the effective limit; move it to Redis if you scale out.
- **Shift times are stored without timezone conversion.** Each site has a
  timezone field, but shift instances are built from naive local times. A
  single-timezone customer is unaffected; a customer spanning timezones needs
  this addressed first.
- **HIPAA/BAA.** This stores physician names, emails, credentials and
  schedules — staffing data, not patient data (no PHI), which is why it isn't
  built as a HIPAA system today. Confirm that boundary before selling into a
  hospital, because any feature touching patient volumes or case data changes
  the answer.
- **No per-tenant encryption or data residency controls**, which larger
  hospital systems ask about during procurement.
