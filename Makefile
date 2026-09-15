# ============================================================================
# NotifyHub — Makefile
#
# Convenzioni per l'help automatico (nessuno script esterno):
#   ##@ Gruppo|descrizione del gruppo     -> intestazione di sezione
#   target: deps ## descrizione           -> voce di target nella sezione corrente
#   ##= descrizione                       -> documenta la variabile `VAR ?= ...`
#   VAR ?= valore                            dichiarata nella riga successiva
# Aggiungendo nuovi target/variabili con questi marcatori, `make help` si
# aggiorna da solo.
# ============================================================================

.DEFAULT_GOAL := help
SHELL := /bin/bash

##@ Aiuto|elenco dei comandi disponibili

.PHONY: help
help: ## Mostra questo elenco (target di default)
	@awk 'BEGIN { \
		FS = ":.*##"; \
		printf "\n\033[1mNotifyHub\033[0m — uso: \033[36mmake\033[0m \033[1m<target>\033[0m [VAR=valore]\n"; \
	} \
	/^##@ / { \
		split(substr($$0, 5), g, "\\|"); \
		printf "\n\033[1;33m%s\033[0m", g[1]; \
		if (g[2] != "") printf " \033[2m— %s\033[0m", g[2]; \
		printf "\n"; \
		next; \
	} \
	/^[a-zA-Z0-9_%.-]+:.*##[^=]/ { \
		printf "  \033[36m%-22s\033[0m %s\n", $$1, substr($$2, 2); \
		next; \
	} \
	/^##=/ { \
		vdesc = substr($$0, 4); sub(/^ */, "", vdesc); \
		next; \
	} \
	/^[A-Z0-9_]+ *\?=/ { \
		if (vdesc != "") { \
			split($$0, v, "?="); \
			name = v[1]; sub(/ *$$/, "", name); \
			val = v[2]; gsub(/^ *| *$$/, "", val); \
			vars[++nv] = sprintf("  \033[36m%-22s\033[0m %s \033[2m(default: %s)\033[0m", name, vdesc, val); \
			vdesc = ""; \
		} \
		next; \
	} \
	END { \
		if (nv > 0) { \
			printf "\n\033[1;33mVariabili\033[0m \033[2m— sovrascrivibili da riga di comando o ambiente\033[0m\n"; \
			for (i = 1; i <= nv; i++) print vars[i]; \
		} \
		printf "\n"; \
	}' $(MAKEFILE_LIST)

##@ Sviluppo|dipendenze, formattazione e analisi statica del backend

.PHONY: install fmt fmt-check lint types

install: ## Installa le dipendenze Python di sviluppo del backend
	pip install -r backend/requirements-dev.txt

fmt: ## Formatta il codice backend (ruff format)
	cd backend && ruff format .

fmt-check: ## Verifica la formattazione backend senza modificare i file
	cd backend && ruff format --check .

lint: ## Esegue il linter backend (ruff check)
	cd backend && ruff check .

types: ## Controlla i tipi del backend (mypy)
	cd backend && mypy

##@ Test|suite backend, copertura, smoke test e gate di qualità

.PHONY: test test-unit test-int cov smoke gates

test: ## Esegue l'intera suite di test backend (pytest)
	cd backend && pytest -q

test-unit: ## Esegue solo i test unit backend
	cd backend && pytest -q -m unit

test-int: ## Esegue solo i test di integrazione backend (richiede up-test)
	cd backend && pytest -q -m integration

cov: ## Esegue i test backend con report di copertura
	cd backend && pytest -q --cov --cov-report=term-missing

smoke: ## Smoke test end-to-end sullo stack containerizzato
	bash scripts/smoke.sh

gates: fmt-check lint types test ## Gate completo backend: fmt-check, lint, types, test

##@ Frontend|lint, test e build della SPA React

.PHONY: fe-lint fe-test fe-cov fe-build

fe-lint: ## Linter frontend (eslint)
	npm --prefix frontend run lint

fe-test: ## Suite di test frontend (vitest)
	npm --prefix frontend run test -- --run

fe-cov: ## Test frontend con report di copertura
	npm --prefix frontend run test -- --coverage

fe-build: ## Build di produzione frontend (tsc + vite)
	npm --prefix frontend run build

##@ Stack locale|ambienti docker compose di sviluppo e di test

.PHONY: up down reset-db up-test down-test migrate migrate-test

up: ## Avvia lo stack di sviluppo in background
	docker compose up -d

down: ## Ferma lo stack di sviluppo
	docker compose down

reset-db: ## Ricrea i volumi di sviluppo (distruttivo sui dati locali)
	docker compose down -v && docker compose up -d

up-test: ## Avvia lo stack di test in background (porte 5433/6380/9002)
	docker compose -f docker-compose.test.yml up -d

down-test: ## Ferma lo stack di test e ne rimuove i volumi
	docker compose -f docker-compose.test.yml down -v

migrate: ## Applica le migrazioni DB allo stack di sviluppo
	cd backend && alembic upgrade head

migrate-test: ## Applica le migrazioni DB allo stack di test
	cd backend && ENV_FILE=.env.test alembic upgrade head

##@ All-in-one|immagine singola con l'intero stack (deploy/all-in-one)

##= Tag di versione dell'immagine all-in-one
ALL_IN_ONE_VERSION ?= 1.0.0
##= Nome dell'immagine all-in-one
ALL_IN_ONE_IMAGE ?= notifyhub-all-in-one

ALL_IN_ONE_DIR := deploy/all-in-one
ALL_IN_ONE_FILE := $(ALL_IN_ONE_DIR)/docker-compose.all-in-one.yml
ALL_IN_ONE_ENV := $(ALL_IN_ONE_DIR)/.env
BUILD_DATE := $(shell date -u +%Y-%m-%dT%H:%M:%SZ)
VCS_REF := $(shell git rev-parse --short HEAD 2>/dev/null || echo unknown)
COMPOSE_ALL_IN_ONE = NOTIFYHUB_IMAGE=$(ALL_IN_ONE_IMAGE) NOTIFYHUB_VERSION=$(ALL_IN_ONE_VERSION) \
	docker compose --env-file $(ALL_IN_ONE_ENV) -f $(ALL_IN_ONE_FILE)

.PHONY: all-in-one-build all-in-one-env all-in-one-up all-in-one-build-up all-in-one-down \
	all-in-one-restart all-in-one-logs all-in-one-ps all-in-one-health all-in-one-shell \
	all-in-one-smoke all-in-one-upgrade all-in-one-backup all-in-one-clean

all-in-one-build: ## Costruisce l'immagine all-in-one
	docker build \
		-f $(ALL_IN_ONE_DIR)/Dockerfile.all \
		--build-arg APP_VERSION=$(ALL_IN_ONE_VERSION) \
		--build-arg BUILD_DATE=$(BUILD_DATE) \
		--build-arg VCS_REF=$(VCS_REF) \
		-t $(ALL_IN_ONE_IMAGE):$(ALL_IN_ONE_VERSION) \
		-t $(ALL_IN_ONE_IMAGE):latest \
		.

all-in-one-env: ## Crea deploy/all-in-one/.env da .env.example se manca
	@test -f $(ALL_IN_ONE_ENV) || cp $(ALL_IN_ONE_DIR)/.env.example $(ALL_IN_ONE_ENV)

all-in-one-up: all-in-one-env ## Avvia lo stack all-in-one in background
	$(COMPOSE_ALL_IN_ONE) up -d

all-in-one-build-up: all-in-one-build ## Costruisce l'immagine e avvia subito lo stack
	$(COMPOSE_ALL_IN_ONE) up -d

all-in-one-down: ## Ferma lo stack all-in-one
	$(COMPOSE_ALL_IN_ONE) down

all-in-one-restart: ## Riavvia lo stack all-in-one
	$(COMPOSE_ALL_IN_ONE) restart

all-in-one-logs: ## Segue i log dello stack all-in-one
	$(COMPOSE_ALL_IN_ONE) logs -f

all-in-one-ps: ## Elenca i container dello stack all-in-one
	$(COMPOSE_ALL_IN_ONE) ps

all-in-one-health: ## Esegue l'healthcheck nel container notifyhub
	$(COMPOSE_ALL_IN_ONE) exec notifyhub notifyhub-healthcheck

all-in-one-shell: ## Apre una shell bash nel container notifyhub
	$(COMPOSE_ALL_IN_ONE) exec notifyhub bash

all-in-one-smoke: ## Smoke test end-to-end dell'immagine all-in-one
	SMOKE_IMAGE=$(ALL_IN_ONE_IMAGE):$(ALL_IN_ONE_VERSION) $(ALL_IN_ONE_DIR)/smoke-all-in-one.sh

##= Immagine gia' installata da cui parte il test di aggiornamento
ALL_IN_ONE_UPGRADE_FROM ?= ghcr.io/manprint/notification-hub:v0.0.3

all-in-one-upgrade: ## Verifica l'aggiornamento da ALL_IN_ONE_UPGRADE_FROM sullo stesso /data
	UPGRADE_FROM_IMAGE=$(ALL_IN_ONE_UPGRADE_FROM) \
	UPGRADE_TO_IMAGE=$(ALL_IN_ONE_IMAGE):$(ALL_IN_ONE_VERSION) \
	$(ALL_IN_ONE_DIR)/upgrade-all-in-one.sh

all-in-one-backup: ## Esegue un backup manuale etichettato
	$(COMPOSE_ALL_IN_ONE) exec notifyhub notifyhub-backup --label manual

all-in-one-clean: ## Distruttivo: elimina i volumi del container unico (serve CONFIRM=yes)
	@test "$(CONFIRM)" = "yes" || { echo "Elimina TUTTI i dati del container unico. Ripetere con CONFIRM=yes"; exit 1; }
	$(COMPOSE_ALL_IN_ONE) down -v
