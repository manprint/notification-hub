# NotifyHub

NotifyHub is a self-hosted, multi-tenant notification aggregation platform. It provides HTTP-based ingestion endpoints identified by receiver slugs, PostgreSQL Row Level Security for data isolation, and asynchronous delivery to Slack and Google Chat.

## Requirements

- Docker and Docker Compose
- Make
- PostgreSQL 16 (via Docker)
- Redis 7 (via Docker)
- MinIO (via Docker)

## Quick Start

Clone the repository and set up the environment:

```bash
cp .env.example .env
make up
make migrate
```

The system will start with bootstrap data. Access the dashboard at `http://localhost`.

## First Notification

Send a test notification:

```bash
# Get a receiver slug from the dashboard, then:
curl -X POST http://localhost/ingest/{receiver_slug} \
  -d "Your message here"
```

## Testing

Run the full test suite:

```bash
make test
```

Run only unit tests:

```bash
make test-unit
```

Run smoke test (end-to-end acceptance):

```bash
bash scripts/smoke.sh
```

## Architecture

- **API**: FastAPI with async PostgreSQL connection pools
- **Data**: PostgreSQL 16 with Row Level Security for multi-tenant isolation
- **Async Tasks**: Celery with Redis broker for notification delivery
- **Storage**: MinIO for payloads larger than 1MB
- **Frontend**: React SPA with TanStack Query
- **Ingestion**: Webhook-compatible HTTP endpoint with rate limiting and idempotency

## Operations

See `docs/OPERAZIONI.md` for production setup, maintenance procedures, and security hardening.
