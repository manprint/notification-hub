import pytest

from app.tasks.celery_app import celery_app

EXPECTED_TASK_NAMES = {
    "app.tasks.delivery.dispatch_delivery",
    "app.tasks.maintenance.purge_notifications",
    "app.tasks.maintenance.purge_deliveries",
    "app.tasks.maintenance.cleanup_tokens",
    "app.tasks.maintenance.reconcile_deliveries",
    "app.tasks.maintenance.drain_object_deletions",
    "app.tasks.maintenance.purge_orphan_objects",
    "app.tasks.maintenance.recompute_tenant_usage",
}


@pytest.mark.unit
def test_celery_app_registra_tutti_i_task_di_delivery_e_maintenance():
    """Il comando reale `celery -A app.tasks.celery_app worker` importa solo questo
    modulo: se non dichiara `include`, i task decorati in app/tasks/delivery.py e
    app/tasks/maintenance.py non vengono mai registrati e il worker parte con
    `[tasks]` vuoto, rifiutando ogni delivery e ogni job di manutenzione con
    'Received unregistered task of type ...'."""
    # Il worker reale importa i moduli elencati in `include` all'avvio, tramite
    # il proprio loader: replichiamo lo stesso passo, altrimenti l'`include`
    # resterebbe una configurazione dichiarata ma mai eseguita in questo test.
    celery_app.loader.import_default_modules()
    assert EXPECTED_TASK_NAMES.issubset(set(celery_app.tasks.keys()))


@pytest.mark.unit
def test_celery_app_instrada_dispatch_delivery_sulla_coda_delivery():
    """spec 8.4, 13: la coda dedicata deve chiamarsi `delivery`."""
    route = celery_app.conf.task_routes["app.tasks.delivery.dispatch_delivery"]
    assert route["queue"] == "delivery"
