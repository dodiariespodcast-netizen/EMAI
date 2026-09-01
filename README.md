# EMAI Scheduler

An AI-driven scheduling platform for emergency medicine physician groups
**and locums/staffing agencies** — the problem ShiftAdmin, Lightning Bolt,
and QGenda solve, built around a constraint-programming solver instead of
manual bidding rounds, with a natural-language layer on top for request
intake and plain-English explanations, full account/identity management
(including "Sign in with Google/Microsoft"), and the compliance tooling a
staffing agency's business actually runs on.

Given a roster, a set of shift requirements, physicians' night/day/weekend
preferences, and their time-off requests, it generates a schedule that:

- **Never** double-books a physician, violates an approved must-have-off
  request, breaks minimum rest rules, or exceeds max-consecutive-shift limits
  (hard constraints).
- **Optimizes** for fairness (workload balanced by FTE), preference
  satisfaction (who wants nights vs. who doesn't), seniority weighting, and
  honoring soft/preferred time-off requests (weighted objective).
- Explains itself in plain English via Claude (optional; falls back to a
  templated summary if no API key is configured).

## Why this is "AI" and not just a solver

The scheduling engine itself is Google OR-Tools' CP-SAT constraint
solver — deterministic and explainable, which matters when the output has
to survive a room full of physicians arguing about who got Christmas off.
A pure LLM cannot reliably guarantee "never double-book anyone" across a
month of shifts; a solver can, by construction. The AI (Claude) layer sits
on top, where it's actually useful:

- **Request intake**: physicians type "I need Dec 22–29 off, it's
  important for my daughter's wedding" instead of filling out a form; it's
  parsed into a structured, prioritized request.
- **Schedule explanations**: every generated schedule gets a natural-
  language summary — what's unfilled and why, who's over/under their
  target, how preference satisfaction shook out — for the medical director
  reviewing the draft before publishing it.

This is also the honest positioning for the business: "AI-powered
scheduling" that is actually a reliable, auditable optimizer with an LLM
concierge layer, not a black box making unaccountable calls about who
works nights.

## Try it in five minutes

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # paste into SECRET_KEY
docker compose up --build
docker compose run --rm api python -m app.seed                  # demo data
```

Then open **http://localhost:5173** and sign in as
`admin@demo-em.example.com` / `demo1234`.

The seed builds a realistic 14-physician group across two sites -- day, swing
and night coverage for four weeks, a mix of employed and locums physicians,
credentials (some expiring), pending and approved time-off requests -- and
runs the optimizer over it, so every screen has real data on it from the
first click. It also prints physician logins so you can see the
self-service side.

Without Docker: `make setup && make seed`, then `make dev-api` and
`make dev-web` in two terminals. `make help` lists everything else.

Deploying for real is covered in **[DEPLOYMENT.md](DEPLOYMENT.md)**.

## What's in the repo

```
backend/    FastAPI + PostgreSQL/SQLite + OR-Tools CP-SAT + Claude
frontend/   React + TypeScript + Tailwind SPA that talks to the API
```

## Backend

### Architecture

```
backend/
  app/
    models/          SQLAlchemy ORM (multi-tenant: everything scoped by org_id)
    schemas/         Pydantic request/response models
    api/routes/      FastAPI routers -- auth, physicians, shifts, requests,
                      schedules, assignments, swaps, credentials, audit,
                      calendar feed
    services/
      scheduling/
        domain.py         Solver-facing dataclasses (DB-independent, unit-testable)
        engine.py         The CP-SAT model: constraints + weighted objective
        service.py        ORM <-> domain adapter, persists ScheduleRun/Assignment
        fairness.py       Per-physician fairness report
        swap_conflicts.py Targeted rest/overlap/eligibility re-check for swap approval
      ai/
        client.py         Anthropic SDK wrapper (returns None if unconfigured)
        request_parser.py NL time-off request -> structured request
        explainer.py       Schedule run -> plain-English summary
      auth/
        oauth.py           Google/Microsoft ID-token verification (JWKS)
      notifications/
        email.py, notify.py  SMTP email, no-op-logs if unconfigured
      audit.py             Append-only audit log helper
      auth/
        password_reset.py    Hashed, single-use invite/reset tokens
    seed.py              Demo-organization loader (`python -m app.seed`)
    core/
      rate_limit.py        Throttles sign-in and email-sending endpoints
      observability.py     Request ids, structured logs, error envelope
  alembic/            DB migrations
  tests/              pytest: solver unit tests + full API workflow tests (62)
```

**Multi-tenant from day one**: every table carries `org_id`; a signup
creates an `Organization` plus its owner `User`. This is a SaaS, not a
single-customer tool. A locums agency's "sites" are its client facilities;
its roster is its contracted physician pool, distinguished by
`employment_type` (employed/locums/contract/moonlighter) and `hourly_rate`.

### The optimizer, briefly

Decision variable `x[physician, shift] ∈ {0,1}`. Hard constraints:
exact coverage per shift (via a heavily-penalized shortfall slack so the
model is never infeasible, it just tells you what it couldn't fill), no
overlapping/insufficient-rest assignments, approved must-off requests,
max consecutive working days, max consecutive nights, per-physician shift
caps. Objective: maximize preference satisfaction (weighted by a
seniority multiplier), honor preferred time-off, minimize deviation from
each physician's FTE-proportional fair share of total/night/weekend
shifts, and crush unfilled-shift count above everything else. See
`app/services/scheduling/engine.py` for the full model with inline
rationale on every constraint.

### Everything beyond the solver

- **Identity**: email/password, plus "Sign in with Google" and "Sign in
  with Microsoft" via ID-token verification (no server-side OAuth code
  exchange needed) -- accounts can link multiple sign-in methods, and an
  admin-invited user's first Google/Microsoft login auto-links by verified
  email.
- **Shift swap marketplace**: a physician offers a shift (to anyone, or a
  named colleague); another claims it; a scheduler approves. Approval
  re-checks rest/overlap/site-eligibility/approved-time-off against the
  claimant's *other* assignments before allowing the reassignment.
- **Credentialing/compliance**: state license, DEA, board certification,
  malpractice insurance, ACLS/BLS/PALS, hospital privileges -- each with an
  expiration date and an `/credentials/expiring?within_days=N` query. This
  is the risk dashboard a locums agency's entire business depends on: an
  expired license is a shift that legally can't be worked.
- **Notifications**: SMTP email on schedule publish, time-off decision,
  and swap claimed/decided; falls back to logging (not failing) when no
  SMTP server is configured.
- **Audit log**: every schedule generation/publish, request decision, and
  swap decision, with who and when -- table stakes for a healthcare-adjacent
  buyer's procurement checklist.
- **Calendar feed**: a token-secured per-physician `.ics` URL, subscribable
  from any phone's calendar app, showing published shifts.
- **Accounts that don't need a human in the loop**: admins invite by email
  and the user sets their own password from a single-use link (no temporary
  passwords passed around); "forgot password" works the same way. Reset
  requests deliberately return the same response whether or not the email
  exists, so the endpoint can't be used to discover who has an account.
- **Manual overrides**: a scheduler can assign, reassign or unassign any
  shift by hand. Overrides run the same hard-rule check the solver does and
  are refused unless explicitly forced -- and a forced override records what
  rule it broke, and why, in the audit log. No scheduling product survives
  contact with reality without this.
- **Reports and exports**: hours and estimated cost per physician for a pay
  period (the billing basis for an agency, payroll for a group), a coverage
  report listing exactly which shifts are still short, plus CSV exports of
  both and of any schedule.
- **Bulk roster import**: onboard a 40-physician group from a CSV, with a
  dry-run mode that validates the file first and reports bad rows by line
  number instead of failing the whole import.
- **Production basics**: rate limiting on sign-in and email endpoints,
  request ids on every response and log line, a `/health/ready` probe that
  actually checks the database, and an error envelope that hands back a
  traceable id instead of a stack trace.

### Running it

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # SQLite by default, zero setup

alembic upgrade head    # or let the app auto-create tables on first boot
uvicorn app.main:app --reload
```

Docs at `http://localhost:8000/docs`. Or via Docker (Postgres included):

```bash
docker compose up --build
```

Run the test suite (62 tests):

```bash
pytest -v
```

To enable Google/Microsoft sign-in, set `GOOGLE_CLIENT_ID` and/or
`MICROSOFT_CLIENT_ID` in `.env` (matching the frontend's
`VITE_GOOGLE_CLIENT_ID`/`VITE_MICROSOFT_CLIENT_ID`) -- each is independently
optional and the corresponding button simply doesn't render if unset. To
enable outbound email, set the `SMTP_*` variables.

### Typical API flow

1. `POST /auth/signup` (or `/auth/oauth/signup`) — creates an org + owner
   user, returns a JWT.
2. `POST /sites`, `POST /shift-types` — define locations and shift patterns
   (e.g. "Day 07–19", "Night 19–07").
3. `POST /shift-instances/generate` — stamp out a month of shift instances
   from a shift type.
4. `POST /physicians` — build the roster, with FTE, night/weekend/holiday
   preference weights (-2..2), employment type, and per-physician rule
   overrides.
5. `POST /time-off-requests` (structured) or
   `POST /time-off-requests/from-text` (natural language) — intake requests;
   `PATCH` to approve/deny.
6. `POST /schedule-runs/generate` — run the optimizer over a date range;
   returns the draft schedule, solver stats, and an AI summary.
7. `GET /schedule-runs/{id}/fairness` — per-physician workload/preference
   report.
8. `POST /schedule-runs/{id}/publish` — lock it in; notifies physicians by
   email.
9. `POST /shift-swaps`, `.../claim`, `.../approve` — the swap marketplace.
10. `POST /credentials`, `GET /credentials/expiring` — compliance tracking.
11. `POST /assignments`, `PATCH`/`DELETE /assignments/{id}` — hand-edit the
    schedule; `GET /shift-instances/{id}/eligible-physicians` says who can
    take a shift and why anyone can't.
12. `GET /reports/hours`, `/reports/coverage`, `/reports/hours.csv`,
    `GET /schedule-runs/{id}/export.csv` — reporting and exports.
13. `POST /physicians/import` — bulk roster CSV (`?dry_run=true` to validate).

`PATCH /scheduling-rules` exposes the objective weights (fairness vs.
preference vs. seniority vs. unfilled-shift penalty) as a per-org dial —
a product lever, not a code change.

## Frontend

A React + TypeScript + Tailwind single-page app (`frontend/`) that covers
the whole backend surface with role-aware views:

- **Auth**: login/signup with email+password or "Continue with
  Google/Microsoft" (via Google Identity Services and MSAL respectively);
  account settings to link/unlink identities and change/set a password.
- **Physician views**: dashboard, a month-grid schedule calendar, time-off
  requests (free-text or a form), standing + time-scoped shift
  preferences, the shift swap marketplace, and their own compliance
  record.
- **Scheduler/admin views**: a first-run setup checklist that walks a new
  group through the dependency order (site → shift types → roster → coverage
  → schedule) and disappears once they're set up; roster management with CSV
  import; sites & shift types; bulk shift-instance generation; schedule
  generation with live solver stats, AI summary, fairness table, CSV export
  and publish; **click-any-shift editing** on the calendar, showing who can
  cover it and why anyone can't; scheduling-rule weight dials; request and
  swap approvals; an org-wide compliance dashboard; an hours/cost and
  coverage report; user invitations and roles; and the audit log.

### Running it

```bash
cd frontend
npm install
cp .env.example .env.local   # point at your backend; OAuth client ids optional
npm run dev
```

Build for production with `npm run build` (outputs to `dist/`, deployable
to any static host in front of the API).

### End-to-end smoke test

`frontend/scripts/e2e-smoke.mjs` drives a full signup-to-published-schedule
flow (plus the physician-side self-service flows) against a real running
backend and built frontend with Playwright/Chromium, asserting zero
console/page errors along the way:

```bash
# terminal 1
cd backend && uvicorn app.main:app --port 8000
# terminal 2
cd frontend && VITE_API_BASE_URL=http://localhost:8000 npm run build && npm run preview -- --port 4173
# terminal 3
cd frontend && npm run e2e:smoke
```

## Turning this into a business

This is built to become a real SaaS product, not a demo, and to sell into
**two related but distinct buyers**:

### 1. Emergency medicine groups (the wedge)

Independent and small-to-mid-size EM groups (5–40 physicians) currently on
spreadsheets, a Facebook-group bidding process, or an underserved corner of
ShiftAdmin/Lightning Bolt. They feel scheduling pain monthly and will pay
to make it go away.

- **Pricing**: per-physician-per-month SaaS ($15–30/physician/mo is in
  line with incumbents), so a 20-physician group is a $300–600/mo account;
  200 such groups is a $1M+ ARR business.
- **Differentiator to sell against ShiftAdmin/Lightning Bolt**:
  natural-language request intake (text instead of a clunky bidding
  portal), a plain-English "why does my schedule look like this"
  explanation, a real shift-swap marketplace instead of a phone tree, and
  a calendar feed that just works on a physician's phone -- the things
  every EM physician actually complains about with incumbent tools.

### 2. Locums and staffing agencies (the higher-ACV expansion)

An agency's business is fundamentally: keep a pool of contracted
physicians compliant (licenses, DEA, malpractice, hospital privileges)
and fill client facilities' shift needs, often across many states. This
product already fits that model without changes to the core:

- One agency = one `Organization`; each client hospital/ED = one `Site`.
  The same solver that balances one EM group's internal fairness works
  identically across an agency's client roster.
- `employment_type` and `hourly_rate` on each physician give the agency
  the pay/contract visibility its billing depends on.
- The **credentialing/expiring-soon dashboard** is the product an agency
  will actually pay the most for -- it's their core operational risk
  (an expired license is a shift that legally cannot be worked, and a
  liability event if missed).
- Per-facility site scoping plus physician eligibility (`site_ids`) models
  "this locum is credentialed at these three hospitals" directly.
- **Pricing**: agencies have materially higher willingness to pay per seat
  (they bill hospitals at a large markup over what they pay physicians) --
  a per-placement or per-active-physician-per-month fee at 3-5x the EM
  group rate is realistic, making a handful of agency accounts worth as
  much ARR as dozens of small EM groups.

### Moat and roadmap

- **Moat**: not the solver (OR-Tools is open source) — it's the
  accumulated rule/preference/compliance data per customer, the trust
  built from a track record of fair, explainable, compliant schedules,
  and the integration surface (API-first specifically so a Slack/SMS bot
  for shift swaps, payroll exports, and EHR/credentialing-verification
  integrations can all be built on top without touching the engine).
- **What's next toward launch**: Stripe usage-based billing hung off the
  existing `Organization.plan_tier` field, SSO/SAML for larger hospital
  systems, mobile push alongside email, a cron job emailing the
  credential-expiry digest the `/credentials/expiring` endpoint already
  computes, and timezone-correct shift times (see the caveats in
  [DEPLOYMENT.md](DEPLOYMENT.md)) before selling into a multi-timezone
  customer.

## Verification

- **62 backend tests** (`make test`) covering the solver in isolation, the
  full API surface, auth/OAuth/reset flows, manual overrides, reports,
  imports, rate limiting, and the demo seed.
- **A 24-step end-to-end browser test** (`frontend/scripts/e2e-smoke.mjs`)
  that drives a real browser against a real backend through the whole
  product: signup → sites → shift types → coverage → roster → CSV import →
  optimizer run → publish → hand-editing shifts on the calendar → reports →
  inviting a user → that user setting their own password from the invite
  link → physician self-service, asserting zero console errors throughout.
- **CI** (`.github/workflows/ci.yml`) runs all of the above on every push,
  plus a migration up/down check and a lint/typecheck/build of the frontend.
