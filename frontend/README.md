# EMAI Scheduler — Frontend

See the [repo root README](../README.md) for the full picture (backend
architecture, business positioning, running both halves together). This
directory is a Vite + React + TypeScript + Tailwind SPA that talks to the
FastAPI backend in `../backend`.

```bash
npm install
cp .env.example .env.local   # point VITE_API_BASE_URL at your backend
npm run dev
```

- `npm run build` — production build to `dist/`
- `npm run lint` — oxlint
- `npm run e2e:smoke` — click-through Playwright smoke test against a
  running backend + built frontend (see `scripts/e2e-smoke.mjs` for setup)
