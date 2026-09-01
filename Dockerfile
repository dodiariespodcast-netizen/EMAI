# Single-container build: the API serves the built frontend from the same
# origin. One service to deploy, no CORS configuration, and no API URL baked
# into the bundle -- the app talks to whatever host served it.
#
#   docker build -t emai-scheduler .
#   docker run -p 8000:8000 -e SECRET_KEY=... emai-scheduler

# ---- stage 1: build the frontend ----
FROM node:22-alpine AS frontend

WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci

# Only set these if you're hosting the frontend somewhere other than this
# container; VITE_API_BASE_URL is deliberately left unset so the bundle uses
# its own origin.
ARG VITE_API_BASE_URL=
ARG VITE_GOOGLE_CLIENT_ID=
ARG VITE_MICROSOFT_CLIENT_ID=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID \
    VITE_MICROSOFT_CLIENT_ID=$VITE_MICROSOFT_CLIENT_ID

COPY frontend/ ./
RUN npm run build

# ---- stage 2: the API, serving that build ----
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STATIC_DIR=/app/static

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend /build/dist /app/static

# Run as a non-root user; nothing here needs to write to the image.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Shell form, so ${PORT} resolves at runtime -- platforms like Render and
# Railway inject their own port and the CMD below honors it.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:%s/health' % os.environ.get('PORT','8000')).status==200 else 1)"

# Migrations run on boot so a fresh database comes up with the current schema.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
