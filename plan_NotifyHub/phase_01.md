# Fase 0 — Scaffolding, tooling, catena dei gate

> **Intent:** creare la struttura del repository, le dipendenze, i servizi di infrastruttura e la catena di gate, in modo che dalla fase 1 in poi esista un comando unico che dice se il lavoro e valido.
> **Shippable alone?** si — al termine il repository e un progetto Python funzionante con un endpoint `/healthz` e i gate verdi. Nessun comportamento di dominio.
> **Preconditions:** nessuna. Il repository contiene solo `notifyhub-spec.md` e `plan_NotifyHub/`.

Tutti i comandi si lanciano dalla radice del repository, cioe la cartella che contiene `notifyhub-spec.md`.

---

## Sub-phases

### 0.1 Struttura delle cartelle e file di servizio

- **Model:** Haiku
- **Files:** creazione di cartelle e file vuoti secondo l'albero qui sotto. Nessun file esistente da modificare.
- **Pattern:** package Python standard, un `__init__.py` vuoto in ogni cartella sotto `backend/app` e `backend/tests`.
- **Change:** crea esattamente questa struttura, niente di piu e niente di meno.

  ```
  backend/app/__init__.py
  backend/app/core/__init__.py
  backend/app/db/__init__.py
  backend/app/models/__init__.py
  backend/app/schemas/__init__.py
  backend/app/api/__init__.py
  backend/app/api/v1/__init__.py
  backend/app/services/__init__.py
  backend/app/outbound/__init__.py
  backend/app/outbound/formatters/__init__.py
  backend/app/tasks/__init__.py
  backend/tests/__init__.py
  backend/tests/unit/__init__.py
  backend/tests/integration/__init__.py
  backend/tests/e2e/__init__.py
  backend/alembic/versions/.gitkeep
  deploy/nginx/.gitkeep
  deploy/postgres/initdb/.gitkeep
  deploy/api/.gitkeep
  deploy/frontend/.gitkeep
  scripts/.gitkeep
  ```

  Crea inoltre `.gitignore` alla radice con esattamente queste righe:

  ```
  __pycache__/
  *.pyc
  .pytest_cache/
  .mypy_cache/
  .ruff_cache/
  .coverage
  htmlcov/
  .env
  node_modules/
  frontend/dist/
  ```

  La cartella `frontend/` non va creata in questa fase: nasce in fase 9 tramite lo scaffolder di Vite.
- **Test strategy:** nessun test, e una sotto-fase puramente strutturale.
- **Unit tests:** nessuno.
- **e2e tests:** nessuno (nessun comportamento).
- **Done:** i file elencati esistono; `find backend -name '__init__.py' | wc -l` restituisce 13.

### 0.2 Dipendenze e configurazione degli strumenti

- **Model:** Haiku
- **Files:** `backend/requirements.txt` (nuovo), `backend/requirements-dev.txt` (nuovo), `backend/pyproject.toml` (nuovo).
- **Change:** scrivi i tre file con questo contenuto esatto. L'elenco delle dipendenze e **chiuso**: nelle fasi successive non si aggiungono pacchetti senza fermarsi e chiedere.

  `backend/requirements.txt`:
  ```
  fastapi~=0.115
  uvicorn[standard]~=0.32
  gunicorn~=23.0
  sqlalchemy~=2.0
  asyncpg~=0.30
  psycopg[binary]~=3.2
  alembic~=1.14
  pydantic~=2.9
  pydantic-settings~=2.6
  email-validator~=2.2
  python-multipart~=0.0.12
  argon2-cffi~=23.1
  pyjwt~=2.9
  cryptography~=43.0
  redis~=5.2
  celery~=5.4
  boto3~=1.35
  aioboto3~=13.2
  google-re2~=1.1
  httpx~=0.27
  structlog~=24.4
  prometheus-client~=0.21
  ```

  `backend/requirements-dev.txt`:
  ```
  -r requirements.txt
  pytest~=8.3
  pytest-asyncio~=0.24
  pytest-cov~=6.0
  respx~=0.21
  freezegun~=1.5
  ruff~=0.8
  mypy~=1.13
  ```

  `backend/pyproject.toml`:
  ```toml
  [tool.ruff]
  line-length = 100
  target-version = "py312"
  src = ["."]

  [tool.ruff.lint]
  select = ["E", "F", "I", "UP", "B", "ASYNC", "S", "T20"]
  ignore = ["S101"]

  [tool.ruff.lint.per-file-ignores]
  "tests/*" = ["S105", "S106"]

  [tool.mypy]
  python_version = "3.12"
  packages = ["app"]
  strict_optional = true
  warn_unused_ignores = true
  disallow_untyped_defs = true
  ignore_missing_imports = true

  [tool.pytest.ini_options]
  asyncio_mode = "auto"
  testpaths = ["tests"]
  markers = [
      "unit: test senza dipendenze esterne",
      "integration: richiede i servizi di docker-compose.test.yml",
      "e2e: percorso completo attraverso l'app ASGI",
  ]
  ```

  La regola ruff `T20` vieta `print`: si usa il logger. La regola `S` e bandit: se segnala un falso positivo, si annota con `# noqa: S<codice>` e una motivazione, non si disattiva la regola globalmente.
- **Test strategy:** un solo test di ambiente, che verifica che le dipendenze critiche siano importabili.
- **Unit tests:** `backend/tests/unit/test_environment.py::test_re2_importabile` — importa `re2`, compila `r"FALL(ITO|IMENT)"`, asserisce che `search("Backup FALLITO")` restituisca un match. Se l'import fallisce, **fermati e chiedi**: non esiste ripiego autorizzato sul modulo `re` (invariante I-3).
- **e2e tests:** nessuno.
- **Done:** `pip install -r backend/requirements-dev.txt` completa senza errori; `pytest backend/tests/unit/test_environment.py -q` passa.

### 0.3 Servizi di infrastruttura e creazione dei ruoli Postgres

- **Model:** Sonnet
- **Files:** `docker-compose.yml` (nuovo), `deploy/postgres/initdb/00-roles.sql` (nuovo), `.env.example` (nuovo).
- **Pattern:** i ruoli si creano nello script di init di Postgres perche `CREATE ROLE` richiede il superutente; tabelle, GRANT e policy arrivano dalle migrazioni (decisione D4 dell'overview).
- **Change:**

  `deploy/postgres/initdb/00-roles.sql` — lo script gira una sola volta, al primo avvio del volume, gia connesso al database indicato da `POSTGRES_DB`. Non nominare il database: cosi lo stesso file serve anche allo stack di test.

  ```sql
  CREATE ROLE notifyhub_owner  LOGIN PASSWORD 'dev_owner'  NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  CREATE ROLE notifyhub_app    LOGIN PASSWORD 'dev_app'    NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  CREATE ROLE notifyhub_ingest LOGIN PASSWORD 'dev_ingest' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  CREATE ROLE notifyhub_auth   LOGIN PASSWORD 'dev_auth'   NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;

  ALTER SCHEMA public OWNER TO notifyhub_owner;
  GRANT USAGE ON SCHEMA public TO notifyhub_app, notifyhub_ingest, notifyhub_auth;
  ```

  Le password sono di sviluppo e stanno nel file apposta: lo stack di esercizio le sovrascrive tramite variabili d'ambiente. Aggiungi in testa al file un commento di una riga che lo dica.

  `docker-compose.yml` — in questa fase contiene **solo** i servizi di infrastruttura. I servizi applicativi (`api`, `worker`, `beat`, `nginx`, `migrate`) arrivano in fase 10.

  - `postgres`: immagine `postgres:16`, `POSTGRES_USER=postgres`, `POSTGRES_PASSWORD=postgres`, `POSTGRES_DB=notifyhub`, porta `5432:5432`, volume nominato `pgdata`, bind mount `./deploy/postgres/initdb:/docker-entrypoint-initdb.d:ro`, healthcheck `pg_isready -U postgres`.
  - `redis`: immagine `redis:7-alpine`, porta `6379:6379`, healthcheck `redis-cli ping`.
  - `minio`: immagine `minio/minio`, comando `server /data --console-address ":9001"`, `MINIO_ROOT_USER=minioadmin`, `MINIO_ROOT_PASSWORD=minioadmin`, porte `9000:9000` e `9001:9001`, volume nominato `miniodata`, healthcheck `mc ready local` oppure `curl -f http://localhost:9000/minio/health/live`.
  - `minio-init`: immagine `minio/mc`, `depends_on: minio: condition: service_healthy`, entrypoint che esegue in sequenza `mc alias set local http://minio:9000 minioadmin minioadmin`, `mc mb --ignore-existing local/notifyhub-payloads`, `mc anonymous set none local/notifyhub-payloads`. Deve terminare con exit 0 e non riavviarsi (`restart: "no"`).

  `.env.example` — elenco completo delle variabili, con i valori di sviluppo:

  ```
  NOTIFYHUB_SECRET_KEY=change-me-32-bytes-minimum-000000
  DATABASE_URL_OWNER=postgresql+asyncpg://notifyhub_owner:dev_owner@localhost:5432/notifyhub
  DATABASE_URL_APP=postgresql+asyncpg://notifyhub_app:dev_app@localhost:5432/notifyhub
  DATABASE_URL_AUTH=postgresql+asyncpg://notifyhub_auth:dev_auth@localhost:5432/notifyhub
  DATABASE_URL_INGEST=postgresql+asyncpg://notifyhub_ingest:dev_ingest@localhost:5432/notifyhub
  DATABASE_URL_SYNC=postgresql+psycopg://notifyhub_app:dev_app@localhost:5432/notifyhub
  REDIS_URL=redis://localhost:6379/0
  CELERY_BROKER_URL=redis://localhost:6379/1
  NOTIFYHUB_S3_ENDPOINT=http://localhost:9000
  NOTIFYHUB_S3_BUCKET=notifyhub-payloads
  NOTIFYHUB_S3_ACCESS_KEY=minioadmin
  NOTIFYHUB_S3_SECRET_KEY=minioadmin
  NOTIFYHUB_S3_REGION=us-east-1
  NOTIFYHUB_INLINE_MAX_BYTES=1048576
  NOTIFYHUB_HARD_MAX_BODY_BYTES=20971520
  ALLOW_PUBLIC_REGISTRATION=false
  NOTIFYHUB_PUBLIC_BASE_URL=http://localhost:5173
  NOTIFYHUB_WEBHOOK_HOST_ALLOWLIST=hooks.slack.com,chat.googleapis.com
  ACCESS_TOKEN_TTL_MINUTES=15
  REFRESH_TOKEN_TTL_DAYS=30
  CORS_ORIGINS=http://localhost:5173
  TRUSTED_PROXIES=
  SMTP_HOST=
  SMTP_PORT=
  SMTP_USER=
  SMTP_PASSWORD=
  SMTP_FROM=
  LOG_LEVEL=INFO
  ```

  Nessun'altra variabile verra introdotta nelle fasi successive. Se una fase sembra richiederne una nuova, **fermati e chiedi**.
- **Test strategy:** verifica manuale con comandi espliciti; il test automatico dei servizi arriva in 0.7.
- **Unit tests:** nessuno.
- **e2e tests:** nessuno.
- **Done:** `docker compose up -d` porta `postgres`, `redis`, `minio` in stato healthy e `minio-init` a exit 0; `docker compose exec postgres psql -U postgres -d notifyhub -c "\du"` elenca i quattro ruoli `notifyhub_*`; `psql "postgresql://notifyhub_app:dev_app@localhost:5432/notifyhub" -c "select 1"` si connette.

### 0.4 Stack di test su porte dedicate

- **Model:** Haiku
- **Files:** `docker-compose.test.yml` (nuovo).
- **Insertion point:** file nuovo, ma i servizi devono rispecchiare `docker-compose.yml` scritto in 0.3, cambiando solo nomi, porte e volumi.
- **Change:** stessi quattro servizi di 0.3, con questi scostamenti e nessun altro:
  - nomi dei servizi con suffisso `-test` (`postgres-test`, `redis-test`, `minio-test`, `minio-init-test`);
  - porte pubblicate `5433:5432`, `6380:6379`, `9002:9000`, `9003:9001`;
  - `POSTGRES_DB=notifyhub_test`;
  - volumi nominati distinti (`pgdata_test`, `miniodata_test`);
  - stesso bind mount di `./deploy/postgres/initdb`, cosi i ruoli esistono anche nel database di test.
- **Test strategy:** nessuna, il file e verificato da 0.7.
- **Unit tests:** nessuno.
- **e2e tests:** nessuno.
- **Done:** `docker compose -f docker-compose.test.yml up -d` porta i tre servizi in healthy; `psql "postgresql://notifyhub_owner:dev_owner@localhost:5433/notifyhub_test" -c "select current_user"` restituisce `notifyhub_owner`.

### 0.5 Makefile

- **Model:** Haiku
- **Files:** `Makefile` (nuovo).
- **Change:** un target per ogni operazione, niente comandi impliciti. I comandi Python girano con `cd backend`. Target richiesti, con esattamente questi nomi:

  | Target | Comando |
  |--------|---------|
  | `install` | `pip install -r backend/requirements-dev.txt` |
  | `up` | `docker compose up -d` |
  | `down` | `docker compose down` |
  | `reset-db` | `docker compose down -v && docker compose up -d` |
  | `up-test` | `docker compose -f docker-compose.test.yml up -d` |
  | `down-test` | `docker compose -f docker-compose.test.yml down -v` |
  | `fmt` | `cd backend && ruff format .` |
  | `fmt-check` | `cd backend && ruff format --check .` |
  | `lint` | `cd backend && ruff check .` |
  | `types` | `cd backend && mypy` |
  | `test` | `cd backend && pytest -q` |
  | `test-unit` | `cd backend && pytest -q -m unit` |
  | `test-int` | `cd backend && pytest -q -m integration` |
  | `migrate` | `cd backend && alembic upgrade head` |
  | `migrate-test` | `cd backend && ENV_FILE=.env.test alembic upgrade head` |
  | `gates` | `$(MAKE) fmt-check && $(MAKE) lint && $(MAKE) types && $(MAKE) test` |
  | `fe-lint` | `npm --prefix frontend run lint` |
  | `fe-test` | `npm --prefix frontend run test -- --run` |
  | `fe-build` | `npm --prefix frontend run build` |

  Aggiungi `.PHONY` con tutti i target. I target `migrate`, `fe-*` falliranno finche le fasi 1 e 9 non li abilitano: e previsto e accettabile.
- **Test strategy:** nessuna.
- **Unit tests:** nessuno.
- **e2e tests:** nessuno.
- **Done:** `make -n gates` stampa i quattro comandi nell'ordine corretto senza eseguirli.

### 0.6 Applicazione FastAPI minima

- **Model:** Sonnet
- **Files:** `backend/app/main.py` (nuovo).
- **Pattern:** application factory. `create_app() -> FastAPI` costruisce e restituisce l'app; il modulo espone anche `app = create_app()` per uvicorn. Tutte le fasi successive registrano i router dentro `create_app`, mai a livello di modulo.
- **Change:** `create_app()` istanzia `FastAPI(title="NotifyHub", version="0.1.0", docs_url="/docs")` e registra un solo endpoint:
  `GET /healthz` che restituisce `{"status": "ok"}` con codice 200, senza toccare database, Redis o MinIO. La verifica delle dipendenze e `/readyz` e arriva in fase 2 sotto-fase 2.6.
  Lascia in `create_app`, subito prima del `return app`, il commento sentinella esatto:
  ```python
  # ROUTERS: i router delle fasi successive si registrano qui sopra
  ```
  Le fasi successive inseriranno le registrazioni immediatamente prima di questo commento.
- **Test strategy:** test e2e in-process con `httpx.ASGITransport`, nessun server avviato.
- **Unit tests:** nessuno.
- **e2e tests:** `T-SCAF1` in `backend/tests/e2e/test_health.py::test_healthz_ritorna_ok` — chiama `GET /healthz` sull'app costruita da `create_app()`, asserisce status 200 e corpo esattamente `{"status": "ok"}`. Test di percorso negativo `T-SCAF2` nello stesso file: `test_rotta_inesistente_ritorna_404` chiama `GET /non-esiste` e asserisce 404; fallisce se qualcuno registra un catch-all.
- **Done:** `make test` verde; `uvicorn app.main:app` da `backend/` risponde 200 su `http://localhost:8000/healthz`.

### 0.7 conftest e verifica dei servizi di test

- **Model:** Sonnet
- **Files:** `backend/tests/conftest.py` (nuovo), `backend/.env.test` (nuovo), `backend/tests/integration/test_services_reachable.py` (nuovo).
- **Insertion point:** `conftest.py` e la radice di tutte le fixture; le fasi successive aggiungono fixture qui e non duplicano setup nei singoli file di test.
- **Pattern:** fixture di sessione per le risorse costose (engine, client S3, client Redis), fixture di funzione per l'isolamento dei dati.
- **Change:**
  - `backend/.env.test` — copia di `.env.example` con host e porte dello stack di test (5433, 6380, 9002) e `POSTGRES_DB=notifyhub_test`. Va versionato: non contiene segreti reali.
  - `conftest.py` definisce:
    - `pytest_configure` che imposta `ENV_FILE=.env.test` se non gia presente, prima di qualunque import di `app.core.config`;
    - fixture di sessione `anyio_backend` che restituisce `"asyncio"`;
    - fixture di sessione `api_client` che costruisce l'app con `create_app()` e restituisce un `httpx.AsyncClient` su `ASGITransport`, con `base_url="http://test"`.
    Le fixture di database, Redis e S3 arrivano nella fase 1 sotto-fase 1.10 e nella fase 5: non anticiparle qui.
  - `test_services_reachable.py` con marker `integration`: tre test che verificano che lo stack di test sia raggiungibile.
- **Test strategy:** questi test sono un canarino sull'ambiente. Devono fallire con un messaggio chiaro se `make up-test` non e stato lanciato.
- **Unit tests:** nessuno.
- **e2e tests:** `T-SCAF3` `test_postgres_raggiungibile` — connessione con `notifyhub_owner` su porta 5433, `SELECT 1`. `T-SCAF4` `test_redis_raggiungibile` — `PING` su 6380 restituisce True. `T-SCAF5` `test_bucket_minio_esiste` — `head_bucket` su `notifyhub-payloads` all'endpoint `http://localhost:9002` non solleva eccezioni. Tutti e tre falliscono se lo stack di test e spento: e il comportamento voluto.
- **Done:** con `make up-test` attivo, `make test` esegue cinque test e sono tutti verdi; con lo stack spento, i tre test `integration` falliscono e i due e2e restano verdi.

---

## Files touched (this phase)

- `.gitignore` — creato — regole di esclusione
- `Makefile` — creato — tutti i comandi operativi
- `docker-compose.yml` — creato — postgres, redis, minio, minio-init
- `docker-compose.test.yml` — creato — stessi servizi su porte 5433/6380/9002/9003
- `.env.example` — creato — elenco chiuso delle variabili d'ambiente
- `deploy/postgres/initdb/00-roles.sql` — creato — i quattro ruoli Postgres
- `backend/requirements.txt` — creato — dipendenze di esercizio
- `backend/requirements-dev.txt` — creato — dipendenze di sviluppo
- `backend/pyproject.toml` — creato — configurazione ruff, mypy, pytest
- `backend/app/main.py` — creato — application factory e `/healthz`
- `backend/.env.test` — creato — configurazione dei test
- `backend/tests/conftest.py` — creato — fixture radice
- `backend/tests/unit/test_environment.py` — creato — T-ENV1
- `backend/tests/e2e/test_health.py` — creato — T-SCAF1, T-SCAF2
- `backend/tests/integration/test_services_reachable.py` — creato — T-SCAF3, T-SCAF4, T-SCAF5
- 13 file `__init__.py` e 5 `.gitkeep` — creati — struttura dei package

---

## Phase gates

- **Fmt:** `make fmt-check`
- **Lint:** `make lint`
- **Tipi:** `make types`
- **Test:** `make up-test && make test`
- **Regression guard:** nessuna fase precedente. Da questa fase in poi, `make gates` deve restare verde al termine di ogni sotto-fase.

## Phase done criterion

Con lo stack di test avviato, `make gates` termina con exit code 0 ed esegue almeno sei test: `T-ENV1`, `T-SCAF1`, `T-SCAF2`, `T-SCAF3`, `T-SCAF4`, `T-SCAF5`. `docker compose exec postgres psql -U postgres -d notifyhub -c "\du"` mostra i quattro ruoli e nessuno di essi ha l'attributo `Bypass RLS`.
