"""Metriche Prometheus, esposte su porta interna 9100 (spec 10.4), mai da nginx.

API e worker sono processi distinti: con PROMETHEUS_MULTIPROC_DIR ognuno scrive i propri
valori in quella directory e il server 9100 li somma (modalita' multiprocess di
prometheus_client). Senza la variabile vale il registro in-process.
"""

import os
import socket

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, make_asgi_app, values
from prometheus_client.multiprocess import MultiProcessCollector
from prometheus_client.registry import REGISTRY

if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
    # Il pid da solo non basta: API e worker sono container diversi e i pid si ripetono.
    # Il collector usa '_' come separatore nei nomi dei file: l'identificativo non lo contiene.
    values.ValueClass = values.MultiProcessValue(
        lambda: f"{socket.gethostname().replace('_', '-')}-{os.getpid()}"
    )


def _registro_metriche() -> CollectorRegistry:
    """Registro letto dal server 9100: con multiprocess somma i file di tutti i processi."""
    if not os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        return REGISTRY
    registro = CollectorRegistry()
    MultiProcessCollector(registro)
    return registro


metrics_app = make_asgi_app(registry=_registro_metriche())

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
    # Ultimo valore scritto, da qualunque processo: dopo un nuovo calcolo (o un restart del worker,
    # che cambia pid) non resta il massimo del passato. Il valore dura fino al ricalcolo successivo,
    # anche con il worker fermo.
    multiprocess_mode="mostrecent",
)
