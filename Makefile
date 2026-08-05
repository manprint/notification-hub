.DEFAULT_GOAL := help

.PHONY: help install up down reset-db up-test down-test fmt fmt-check lint types test test-unit test-int migrate migrate-test gates fe-lint fe-test fe-build \
	all-in-one-build all-in-one-env all-in-one-up all-in-one-down all-in-one-restart all-in-one-logs all-in-one-ps \
	all-in-one-health all-in-one-shell all-in-one-smoke all-in-one-backup all-in-one-clean \
	all-in-one-build-up \
	cov fe-cov

# ---------------------------------------------------------------------------
# sviluppo: tooling e gate del progetto
# ---------------------------------------------------------------------------

# Mostra questo elenco di target (target di default di make).
help:
	@awk -f scripts/make-help.awk Makefile

# Installa le dipendenze Python del backend.
install:
	pip install -r backend/requirements-dev.txt

# Avvia lo stack di sviluppo in background.
up:
	docker compose up -d

# Ferma lo stack di sviluppo.
down:
	docker compose down

# Ricrea i volumi di sviluppo (distruttivo sui dati locali).
reset-db:
	docker compose down -v && docker compose up -d

# Avvia lo stack di test in background.
up-test:
	docker compose -f docker-compose.test.yml up -d

# Ferma e rimuove i volumi dello stack di test.
down-test:
	docker compose -f docker-compose.test.yml down -v

# Formatta automaticamente il codice backend (ruff).
fmt:
	cd backend && ruff format .

# Verifica la formattazione backend senza modificare i file.
fmt-check:
	cd backend && ruff format --check .

# Esegue il linter backend (ruff check).
lint:
	cd backend && ruff check .

# Controlla i tipi backend (mypy).
types:
	cd backend && mypy

# Esegue l'intera suite di test backend (pytest).
test:
	cd backend && pytest -q

# Esegue solo i test unit backend.
test-unit:
	cd backend && pytest -q -m unit

# Esegue solo i test di integrazione backend.
test-int:
	cd backend && pytest -q -m integration

# Applica le migrazioni DB allo stack di sviluppo.
migrate:
	cd backend && alembic upgrade head

# Applica le migrazioni DB allo stack di test.
migrate-test:
	cd backend && ENV_FILE=.env.test alembic upgrade head

# Esegue i test backend con report di copertura.
cov:
	cd backend && pytest -q --cov --cov-report=term-missing

# Esegue i test frontend con report di copertura.
fe-cov:
	npm --prefix frontend run test -- --coverage

# Gate completo backend: fmt-check, lint, types, test.
gates: fmt-check lint types test

# Linter frontend (eslint).
fe-lint:
	npm --prefix frontend run lint

# Suite di test frontend (vitest).
fe-test:
	npm --prefix frontend run test -- --run

# Build di produzione frontend (tsc + vite).
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

# Costruisce l'immagine all-in-one.
all-in-one-build:
	docker build \
		-f $(ALL_IN_ONE_DIR)/Dockerfile.all \
		--build-arg APP_VERSION=$(ALL_IN_ONE_VERSION) \
		--build-arg BUILD_DATE=$(BUILD_DATE) \
		--build-arg VCS_REF=$(VCS_REF) \
		-t $(ALL_IN_ONE_IMAGE):$(ALL_IN_ONE_VERSION) \
		-t $(ALL_IN_ONE_IMAGE):latest \
		.

# Crea .env da .env.example se non esiste.
all-in-one-env:
	@test -f $(ALL_IN_ONE_ENV) || cp $(ALL_IN_ONE_DIR)/.env.example $(ALL_IN_ONE_ENV)

# Avvia lo stack all-in-one in background.
all-in-one-up: all-in-one-env
	$(COMPOSE_ALL_IN_ONE) up -d

# Costruisce l'immagine e avvia subito lo stack in background.
all-in-one-build-up: all-in-one-build
	$(COMPOSE_ALL_IN_ONE) up -d

# Ferma lo stack all-in-one.
all-in-one-down:
	$(COMPOSE_ALL_IN_ONE) down

# Riavvia lo stack all-in-one.
all-in-one-restart:
	$(COMPOSE_ALL_IN_ONE) restart

# Segue i log dello stack all-in-one.
all-in-one-logs:
	$(COMPOSE_ALL_IN_ONE) logs -f

# Elenca i container dello stack all-in-one.
all-in-one-ps:
	$(COMPOSE_ALL_IN_ONE) ps

# Esegue l'healthcheck nel container notifyhub.
all-in-one-health:
	$(COMPOSE_ALL_IN_ONE) exec notifyhub notifyhub-healthcheck

# Apre una shell bash nel container notifyhub.
all-in-one-shell:
	$(COMPOSE_ALL_IN_ONE) exec notifyhub bash

# Esegue lo smoke test end-to-end dell'immagine.
all-in-one-smoke:
	SMOKE_IMAGE=$(ALL_IN_ONE_IMAGE):$(ALL_IN_ONE_VERSION) $(ALL_IN_ONE_DIR)/smoke-all-in-one.sh

# Esegue un backup manuale etichettato.
all-in-one-backup:
	$(COMPOSE_ALL_IN_ONE) exec notifyhub notifyhub-backup --label manual

# Distruttivo: elimina i volumi del container unico (serve CONFIRM=yes).
all-in-one-clean:
	@test "$(CONFIRM)" = "yes" || { echo "Elimina TUTTI i dati del container unico. Ripetere con CONFIRM=yes"; exit 1; }
	$(COMPOSE_ALL_IN_ONE) down -v
