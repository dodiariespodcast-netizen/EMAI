# Common tasks. `make help` lists them.
.DEFAULT_GOAL := help
.PHONY: help setup dev-api dev-web test lint build seed reset-demo migrate up down logs clean

BACKEND := backend
FRONTEND := frontend
VENV := $(BACKEND)/.venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## Install backend + frontend dependencies
	python3 -m venv $(VENV)
	$(PIP) install -q -r $(BACKEND)/requirements-dev.txt
	cd $(FRONTEND) && npm install
	@test -f $(BACKEND)/.env || cp $(BACKEND)/.env.example $(BACKEND)/.env
	@test -f $(FRONTEND)/.env.local || cp $(FRONTEND)/.env.example $(FRONTEND)/.env.local
	@echo "\nReady. Run 'make seed' for demo data, then 'make dev-api' and 'make dev-web'."

dev-api: ## Run the API with reload on :8000
	cd $(BACKEND) && .venv/bin/uvicorn app.main:app --reload --port 8000

dev-web: ## Run the frontend dev server on :5173
	cd $(FRONTEND) && npm run dev

test: ## Run the backend test suite
	cd $(BACKEND) && .venv/bin/pytest -q

lint: ## Lint the frontend
	cd $(FRONTEND) && npm run lint

build: ## Typecheck and build the frontend
	cd $(FRONTEND) && npm run build

seed: ## Load the demo organization (admin@demo-em.example.com / demo1234)
	cd $(BACKEND) && .venv/bin/python -m app.seed

reset-demo: ## Wipe and reload the demo organization
	cd $(BACKEND) && .venv/bin/python -m app.seed --reset

migrate: ## Apply database migrations
	cd $(BACKEND) && .venv/bin/alembic upgrade head

up: ## Start the whole stack in Docker
	docker compose up --build

down: ## Stop the Docker stack
	docker compose down

logs: ## Tail Docker logs
	docker compose logs -f

clean: ## Remove build artifacts, caches and local databases
	rm -rf $(FRONTEND)/dist $(FRONTEND)/node_modules/.vite
	find $(BACKEND) -name __pycache__ -type d -prune -exec rm -rf {} +
	find $(BACKEND) -name '*.db' -delete
