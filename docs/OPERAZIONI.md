# Guida Operativa NotifyHub

## Messa in Produzione

### Cambio Password Predefinite

Prima di esporre NotifyHub su Internet, modificare le password di default dei quattro ruoli PostgreSQL e dell'accesso MinIO:

#### PostgreSQL (docker-compose.yml)

```bash
# Genera password sicure
openssl rand -base64 32

# Aggiorna le variabili in .env:
DATABASE_PASSWORD=<nuova_password>
DATABASE_OWNER_PASSWORD=<nuova_password_owner>
```

Esegui le migrazioni dopo il cambio per garantire che i ruoli siano creati con le nuove credenziali.

#### MinIO (docker-compose.yml)

```bash
# Aggiorna .env:
MINIO_ROOT_USER=<nuovo_user>
MINIO_ROOT_PASSWORD=<nuova_password>
```

Ricrea il bucket `notifyhub-payloads` dopo il cambio di credenziali:

```bash
docker compose down
docker compose up -d minio minio-init
```

### Terminazione TLS

nginx ascolta sulla porta 80 senza TLS. Per la produzione:

1. Ottieni un certificato SSL (Let's Encrypt, self-signed, etc.)
2. Modifica `deploy/nginx/nginx.conf`:

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;
    
    ssl_certificate /etc/nginx/certs/cert.pem;
    ssl_certificate_key /etc/nginx/certs/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    
    # ... resto della configurazione ...
}
```

3. Monta i certificati nel container nginx via `volumes`.

## Variabili d'Ambiente

| Variabile | Descrizione | Default |
|-----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string (notifyhub_app) | postgresql://... |
| `DATABASE_OWNER_PASSWORD` | Password for schema owner (Alembic) | postgres |
| `REDIS_URL` | Redis connection string | redis://redis:6379/0 |
| `MINIO_ENDPOINT` | MinIO S3-compatible endpoint | minio:9000 |
| `MINIO_ACCESS_KEY` | MinIO access key | minioadmin |
| `MINIO_SECRET_KEY` | MinIO secret key | minioadmin |
| `NOTIFYHUB_WEBHOOK_HOST_ALLOWLIST` | Comma-separated webhook hosts | slack.com,google.com |
| `NOTIFYHUB_PAYLOAD_THRESHOLD_BYTES` | Inline/object storage threshold | 1048576 (1MB) |
| `NOTIFYHUB_MAX_DELIVERY_ATTEMPTS` | Max retries for webhook delivery | 5 |
| `NOTIFYHUB_BASE_RETRY_SECONDS` | Base retry delay (exponential backoff) | 2 |

## Job di Manutenzione

Seven background jobs run via Celery Beat. Tutti leggono configurazione da variabili d'ambiente oppure hanno default ragionevoli.

### 1. `reconcile_pending_deliveries`

**Cosa fa:** ricerca delivery con stato `pending` o `sending` da più di 5 minuti e ri-accoda per la consegna.

**Quando:** ogni 5 minuti

**Importanza:** CRITICA. Se il broker Redis perde messaggi, questo job garantisce consegna asincrona.

**Se non gira:** notifiche restano bloccate; incrementare la frequenza o controllare che il worker sia attivo.

### 2. `purge_orphan_objects`

**Cosa fa:** ricerca entry in `pending_object_deletions` più vecchie di 1 giorno e cancella i blob da MinIO.

**Quando:** ogni ora

**Importanza:** MEDIA. Previene accumulo indefinito di oggetti orfani su MinIO.

**Se non gira:** disk space MinIO cresce lentamente; esegui manualmente:

```bash
docker compose run --rm worker celery -A app.tasks.celery_app call app.tasks.maintenance.purge_orphan_objects
```

### 3. `clear_expired_tokens`

**Cosa fa:** cancella `refresh_tokens` scaduti e `invitations` scadute (> 7 giorni).

**Quando:** ogni 24 ore

**Importanza:** BASSA. Pulizia housekeeping.

**Se non gira:** database cresce leggermente; non critico.

### 4. `reap_completed_migrations`

**Cosa fa:** cancella record di migrazioni completate più vecchi di 30 giorni.

**Quando:** ogni 7 giorni

**Importanza:** BASSA. Evita crescita dei log di migrazione.

### 5. `detect_tenant_suspension`

**Cosa fa:** controlla se tenant hanno raggiunto limiti di quota e li sospende.

**Quando:** ogni 30 minuti

**Importanza:** MEDIA. Richiede `NOTIFYHUB_QUOTA_CHECKS=true` in .env.

**Se non gira:** tenant possono superare quota; controllare che `enable_quota_enforcement` sia true.

### 6. `sync_external_webhooks`

**Cosa fa:** sincronizza lo stato di delivery channels esterni (se configurato).

**Quando:** ogni 60 minuti

**Importanza:** BASSA. Solo se integrato con external system.

### 7. `log_metrics_summary`

**Cosa fa:** log aggregato di metriche giornaliere (notification count, delivery success rate, etc.).

**Quando:** ogni 24 ore a mezzanotte UTC

**Importanza:** BASSA. Solo per observability.

## Backup e Ripristino

I dati vivono in tre posti:

1. **PostgreSQL**: tabelle, schema, constraints, RLS policies
2. **MinIO**: blob di notifiche > 1MB
3. **Redis**: state transitorio (rate limit, lock, broker queue)

### Backup Coordinato

Sempre fare backup di PostgreSQL e MinIO insieme:

```bash
# Backup PostgreSQL
docker compose exec -T postgres pg_dump -U postgres notifyhub > backup.sql

# Backup MinIO
docker compose run --rm mc alias set local http://minio:9000 minioadmin minioadmin
docker compose run --rm mc mirror local/notifyhub-payloads ./minio-backup/
```

### Ripristino

```bash
# Ripristina database
docker compose exec -T postgres psql -U postgres notifyhub < backup.sql

# Ripristina MinIO
docker compose run --rm mc alias set local http://minio:9000 minioadmin minioadmin
docker compose run --rm mc mirror ./minio-backup/ local/notifyhub-payloads
```

## Troubleshooting

### `pending_object_deletions_backlog` cresce

Significa che il job `purge_orphan_objects` non riesce a contattare MinIO o i file sono gia cancellati.

**Diagnostica:**

```bash
docker compose logs worker | grep purge_orphan
docker compose exec minio mc ls local/notifyhub-payloads
```

**Fix:** riavvia il worker e controlla la connessione MinIO.

### Rate limiting bloccato

Se tutti i receiver hanno 0 richieste rimaste, controllare Redis:

```bash
docker compose exec redis redis-cli
> KEYS "rate_limit:*"
> DEL rate_limit:*  # Reset globale
```

### RLS blocca query legittime

Se un utente vede 403 su endpoint válido, controllare che `app.tenant_id` sia impostato. Nel codice deve esserci un commit di transazione con `SET LOCAL`:

```python
await session.execute(text("SET LOCAL app.tenant_id = :tenant_id"), {"tenant_id": tenant_id})
```

### Webhook non inoltrati

Controllare che il worker sia attivo:

```bash
docker compose logs worker
docker compose exec worker celery -A app.tasks.celery_app inspect active
```

Se nessun task è attivo, il worker è morto; riavvia:

```bash
docker compose restart worker
```

## Metriche Esposte

L'API espone metriche Prometheus sulla porta interna 9100 (non visibile da nginx):

```bash
curl http://localhost:9100/metrics
```

Metriche principali:

- `notifyhub_notifications_ingested_total`: counter, notifiche ricevute
- `notifyhub_notifications_forwarded_total`: counter, notifiche inoltrate a webhook
- `notifyhub_delivery_failed_total`: counter, fallimenti di consegna
- `notifyhub_ingestion_request_duration_seconds`: histogram, latenza ingestion
- `notifyhub_receiver_rate_limit_exceeded`: gauge, quanti receiver hanno superato limite

Integra con Prometheus aggiungendo un job di scrape verso il container API:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: notifyhub
    static_configs:
      - targets: ['api:9100']
```

## Limitazioni Conosciute

- L'ingestion endpoint non supporta streaming incrementale (carica tutto in memoria, poi valida)
- I webhook falliti non vengono mai cancellati; restano con stato `failed` indefinitamente
- Nessun limite per il numero di severity rules per receiver
- RLS non supporta query cross-tenant (by design)

## Support

Per bug o feature request, consultare il documento di spec: `notifyhub-spec.md`.
