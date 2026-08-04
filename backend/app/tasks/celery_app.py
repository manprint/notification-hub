"""Configurazione Celery (spec 8.4, 13): coda `delivery`, broker Redis."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "notifyhub",
    broker=settings.celery_broker_url,
    include=["app.tasks.delivery", "app.tasks.maintenance"],
)

celery_app.conf.update(
    task_routes={
        "app.tasks.delivery.dispatch_delivery": {"queue": "delivery"},
    },
    task_serializer="json",
    accept_content=["json"],
    result_backend=None,
    # Orari fissi come da spec 11: notturni per non contendere con il picco di
    # traffico, sfalsati fra loro per non accodare tutti i job insieme.
    beat_schedule={
        "purge-notifications": {
            "task": "app.tasks.maintenance.purge_notifications",
            "schedule": crontab(hour=3, minute=0),
        },
        "purge-deliveries": {
            "task": "app.tasks.maintenance.purge_deliveries",
            "schedule": crontab(hour=3, minute=30),
        },
        "cleanup-tokens": {
            "task": "app.tasks.maintenance.cleanup_tokens",
            "schedule": crontab(minute=0),
        },
        "reconcile-deliveries": {
            "task": "app.tasks.maintenance.reconcile_deliveries",
            "schedule": 300,
        },
        "drain-object-deletions": {
            "task": "app.tasks.maintenance.drain_object_deletions",
            "schedule": 600,
        },
        "purge-orphan-objects": {
            "task": "app.tasks.maintenance.purge_orphan_objects",
            "schedule": crontab(hour=4, minute=0),
        },
        # Sorveglianza dell'attesa: ogni minuto, perche' la tolleranza piu'
        # piccola che si possa configurare e' dell'ordine dei minuti e un job che
        # gira ogni ora renderebbe l'allarme inutilmente tardivo. Costa una query
        # indicizzata per tenant sui soli receiver sorvegliati.
        "check-expected-schedules": {
            "task": "app.tasks.maintenance.check_expected_schedules",
            "schedule": 60,
        },
        "recompute-tenant-usage": {
            "task": "app.tasks.maintenance.recompute_tenant_usage",
            "schedule": crontab(hour=4, minute=30),
        },
    },
)
