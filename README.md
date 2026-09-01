# EMAI Scheduler

An AI-driven scheduling backend for emergency medicine physician groups —
the same problem ShiftAdmin/Lightning Bolt/QGenda solve, built around a
constraint-programming solver instead of manual bidding rounds, with a
natural-language layer on top for request intake and plain-English
explanations of every schedule it produces.

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

## Architecture

```
backend/
  app/
    models/          SQLAlchemy ORM (multi-tenant: everything scoped by org_id)
    schemas/         Pydantic request/response models
    api/routes/       FastAPI routers (auth, physicians, shifts, requests, schedules)
    services/
      scheduling/
        domain.py     Solver-facing dataclasses (DB-independent, unit-testable)
        engine.py     The CP-SAT model: constraints + weighted objective
        service.py    ORM <-> domain adapter, persists ScheduleRun/Assignment
        fairness.py   Per-physician fairness report
      ai/
        client.py         Anthropic SDK wrapper (returns None if unconfigured)
        request_parser.py NL time-off request -> structured request
        explainer.py       Schedule run -> plain-English summary
  alembic/            DB migrations
  tests/              pytest: solver unit tests + full API workflow test
```

**Multi-tenant from day one**: every table carries `org_id`; a signup
creates an `Organization` plus its owner `User`. This is a SaaS, not a
single-customer tool.

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

## Running it

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

Run the test suite:

```bash
pytest -v
```

## Typical API flow

1. `POST /auth/signup` — creates an org + owner user, returns a JWT.
2. `POST /sites`, `POST /shift-types` — define locations and shift patterns
   (e.g. "Day 07–19", "Night 19–07").
3. `POST /shift-instances/generate` — stamp out a month of shift instances
   from a shift type.
4. `POST /physicians` — build the roster, with FTE, night/weekend/holiday
   preference weights (-2..2), and per-physician rule overrides.
5. `POST /time-off-requests` (structured) or
   `POST /time-off-requests/from-text` (natural language) — intake requests;
   `PATCH` to approve/deny.
6. `POST /schedule-runs/generate` — run the optimizer over a date range;
   returns the draft schedule, solver stats, and an AI summary.
7. `GET /schedule-runs/{id}/fairness` — per-physician workload/preference
   report.
8. `POST /schedule-runs/{id}/publish` — lock it in.

`PATCH /scheduling-rules` exposes the objective weights (fairness vs.
preference vs. seniority vs. unfilled-shift penalty) as a per-org dial —
a product lever, not a code change.

## Turning this into a business

This is built to become a real SaaS product, not a demo:

- **Wedge**: independent and small-to-mid-size emergency medicine groups
  (5–40 physicians) currently on spreadsheets, a Facebook group bidding
  process, or an underserved corner of ShiftAdmin/Lightning Bolt. They feel
  scheduling pain monthly and will pay to make it go away.
- **Pricing**: per-physician-per-month SaaS ($15–30/physician/mo is in
  line with incumbents), so a 20-physician group is a $300–600/mo account;
  200 such groups is a $1M+ ARR business.
  - **Differentiator to sell against ShiftAdmin/Lightning Bolt**: natural-
    language request intake (text instead of a clunky bidding portal) and
    a plain-English "why does my schedule look like this" explanation —
    the two things every EM physician actually complains about with
    incumbent tools.
- **Expansion**: the multi-tenant/`org_id` model and site-scoped rosters
  already support multi-site hospital systems and staffing agencies as a
  higher-ACV tier; the same engine generalizes to hospitalists, anesthesia,
  and other shift-based specialties with a different set of shift
  categories, which is the natural vertical-expansion path.
- **Moat**: not the solver (OR-Tools is open source) — it's the accumulated
  rule/preference data per customer, the trust built from a track record of
  fair, explainable schedules, and the integration surface (this backend is
  designed API-first specifically so a scheduling front end, a Slack/SMS
  bot for shift swaps, and calendar/EHR integrations can all be built on
  top without touching the engine).
- **What's next toward launch**: a scheduler-facing web UI (this backend is
  API-complete for one), shift-swap/trade workflows, calendar export
  (ICS/Google), audit logging, SSO, and usage-based billing (Stripe) hung
  off the existing `Organization.plan_tier` field.
