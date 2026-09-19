SHELL := /bin/sh
BACKEND_DIR := backend
FRONTEND_DIR := frontend

.PHONY: help install install-backend install-frontend dev up down logs build migrate seed-demo \
	lint typecheck test test-unit test-integration test-contract test-e2e frontend-build clean

help:
	@echo "FirstComment Agent"
	@echo "  make install          Install backend and frontend dependencies"
	@echo "  make up               Start the complete Docker Compose stack"
	@echo "  make migrate          Upgrade the database to the latest migration"
	@echo "  make seed-demo        Seed a local demonstration workspace"
	@echo "  make lint             Run backend and frontend lint checks"
	@echo "  make typecheck        Run Python and TypeScript type checks"
	@echo "  make test             Run all repository tests"

install: install-backend install-frontend

install-backend:
	python3 -m pip install -e "$(BACKEND_DIR)[dev]"

install-frontend:
	npm --prefix $(FRONTEND_DIR) install

dev:
	docker compose up --build

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

build:
	docker compose build

migrate:
	docker compose run --rm backend-api alembic upgrade head

seed-demo:
	docker compose run --rm backend-api python /workspace/scripts/seed_demo.py

lint:
	cd $(BACKEND_DIR) && ruff check .
	npm --prefix $(FRONTEND_DIR) run lint

typecheck:
	cd $(BACKEND_DIR) && mypy app
	npm --prefix $(FRONTEND_DIR) run typecheck

test-unit:
	cd $(BACKEND_DIR) && pytest app/tests/unit

test-integration:
	cd $(BACKEND_DIR) && pytest app/tests/integration

test-contract:
	cd $(BACKEND_DIR) && pytest app/tests/contract

test-e2e:
	cd $(BACKEND_DIR) && pytest app/tests/e2e

test: test-unit test-integration test-contract test-e2e frontend-build

frontend-build:
	npm --prefix $(FRONTEND_DIR) run build

clean:
	find $(BACKEND_DIR) -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf $(FRONTEND_DIR)/.next $(FRONTEND_DIR)/node_modules
