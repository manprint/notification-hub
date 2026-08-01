.PHONY: install up down reset-db up-test down-test fmt fmt-check lint types test test-unit test-int migrate migrate-test gates fe-lint fe-test fe-build

install:
	pip install -r backend/requirements-dev.txt

up:
	docker compose up -d

down:
	docker compose down

reset-db:
	docker compose down -v && docker compose up -d

up-test:
	docker compose -f docker-compose.test.yml up -d

down-test:
	docker compose -f docker-compose.test.yml down -v

fmt:
	cd backend && ruff format .

fmt-check:
	cd backend && ruff format --check .

lint:
	cd backend && ruff check .

types:
	cd backend && mypy

test:
	cd backend && pytest -q

test-unit:
	cd backend && pytest -q -m unit

test-int:
	cd backend && pytest -q -m integration

migrate:
	cd backend && alembic upgrade head

migrate-test:
	cd backend && ENV_FILE=.env.test alembic upgrade head

gates: fmt-check lint types test

fe-lint:
	npm --prefix frontend run lint

fe-test:
	npm --prefix frontend run test -- --run

fe-build:
	npm --prefix frontend run build
