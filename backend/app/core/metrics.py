"""Metriche Prometheus, esposte su porta interna 9100 (spec 10.4), mai da nginx."""

from prometheus_client import Counter, Gauge, Histogram, make_asgi_app

metrics_app = make_asgi_app()

ingestion_requests_total = Counter(
    "notifyhub_ingestion_requests_total",
    "Richieste di ingestion per esito",
    ["outcome"],
)

ingestion_duration_seconds = Histogram(
    "notifyhub_ingestion_duration_seconds",
    "Latenza dell'endpoint di ingestion",
)

deliveries_total = Counter(
    "notifyhub_deliveries_total",
    "Tentativi di inoltro per esito",
    ["outcome"],
)

maintenance_job_runs_total = Counter(
    "notifyhub_maintenance_job_runs_total",
    "Esecuzioni dei job di manutenzione per esito",
    ["job", "outcome"],
)

tenant_storage_bytes = Gauge(
    "notifyhub_tenant_storage_bytes",
    "Spazio occupato per tenant (inline + oggetti MinIO), da recompute_tenant_usage",
    ["tenant_id"],
)
