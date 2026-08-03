.PHONY: install up down reset-db up-test down-test fmt fmt-check lint types test test-unit test-int migrate migrate-test gates fe-lint fe-test fe-build \
	all-in-one-build all-in-one-env all-in-one-up all-in-one-down all-in-one-restart all-in-one-logs all-in-one-ps \
	all-in-one-health all-in-one-shell all-in-one-smoke all-in-one-backup all-in-one-clean

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

# ---------------------------------------------------------------------------
# immagine all-in-one: tutto lo stack in un solo container (deploy/all-in-one)
# ---------------------------------------------------------------------------

ALL_IN_ONE_VERSION ?= 1.0.0
ALL_IN_ONE_IMAGE ?= notifyhub-all-in-one
ALL_IN_ONE_DIR := deploy/all-in-one
ALL_IN_ONE_FILE := $(ALL_IN_ONE_DIR)/docker-compose.all-in-one.yml
ALL_IN_ONE_ENV := $(ALL_IN_ONE_DIR)/.env
BUILD_DATE := $(shell date -u +%Y-%m-%dT%H:%M:%SZ)
VCS_REF := $(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)
COMPOSE_ALL_IN_ONE = NOTIFYHUB_IMAGE=$(ALL_IN_ONE_IMAGE) NOTIFYHUB_VERSION=$(ALL_IN_ONE_VERSION) \
	docker compose --env-file $(ALL_IN_ONE_ENV) -f $(ALL_IN_ONE_FILE)

all-in-one-build:
	docker build \
		-f $(ALL_IN_ONE_DIR)/Dockerfile.all \
		--build-arg APP_VERSION=$(ALL_IN_ONE_VERSION) \
		--build-arg BUILD_DATE=$(BUILD_DATE) \
		--build-arg VCS_REF=$(VCS_REF) \
		-t $(ALL_IN_ONE_IMAGE):$(ALL_IN_ONE_VERSION) \
		-t $(ALL_IN_ONE_IMAGE):latest \
		.

# Il compose interpola le variabili da questo file: se manca, si parte dall'esempio.
all-in-one-env:
	@test -f $(ALL_IN_ONE_ENV) || cp $(ALL_IN_ONE_DIR)/.env.example $(ALL_IN_ONE_ENV)

all-in-one-up: all-in-one-env
	$(COMPOSE_ALL_IN_ONE) up -d

all-in-one-down:
	$(COMPOSE_ALL_IN_ONE) down

all-in-one-restart:
	$(COMPOSE_ALL_IN_ONE) restart

all-in-one-logs:
	$(COMPOSE_ALL_IN_ONE) logs -f

all-in-one-ps:
	$(COMPOSE_ALL_IN_ONE) ps

all-in-one-health:
	$(COMPOSE_ALL_IN_ONE) exec notifyhub notifyhub-healthcheck

all-in-one-shell:
	$(COMPOSE_ALL_IN_ONE) exec notifyhub bash

all-in-one-smoke:
	SMOKE_IMAGE=$(ALL_IN_ONE_IMAGE):$(ALL_IN_ONE_VERSION) $(ALL_IN_ONE_DIR)/smoke-all-in-one.sh

all-in-one-backup:
	$(COMPOSE_ALL_IN_ONE) exec notifyhub notifyhub-backup --label manual

# Distruttivo: elimina i volumi con database, oggetti MinIO, configurazione e log.
all-in-one-clean:
	@test "$(CONFIRM)" = "yes" || { echo "Elimina TUTTI i dati del container unico. Ripetere con CONFIRM=yes"; exit 1; }
	$(COMPOSE_ALL_IN_ONE) down -v
