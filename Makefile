.PHONY: install dev api web test test-backend test-frontend build

install:
	cd backend && uv sync --all-groups
	cd frontend && pnpm install --frozen-lockfile

dev:
	./scripts/dev.sh

api:
	cd backend && uv run uvicorn cost_data.main:app --reload --host 127.0.0.1 --port 8765

web:
	cd frontend && pnpm dev

test: test-backend test-frontend

test-backend:
	cd backend && uv run pytest

test-frontend:
	cd frontend && pnpm test -- --run

build:
	cd frontend && pnpm build

