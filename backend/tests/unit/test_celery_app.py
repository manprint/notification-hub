import configparser
import json
import re
import shlex
from pathlib import Path

import pytest

from app.tasks.celery_app import celery_app

# Radice del repository: backend/tests/unit/ -> tre livelli sopra backend/.
REPO_ROOT = Path(__file__).resolve().parents[3]

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


def _code_queues_from_compose() -> set[str]:
    """Code consumate dal worker in docker-compose.yml (riga `command:` JSON-style)."""
    text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    match = re.search(r"command: (\[[^\n]*\"-Q\"[^\n]*\])", text)
    assert match is not None, "comando del worker con -Q non trovato in docker-compose.yml"
    args = json.loads(match.group(1))
    return set(args[args.index("-Q") + 1].split(","))


def _code_queues_from_supervisord() -> set[str]:
    """Code consumate dal programma `worker` di deploy/all-in-one/config/supervisord.conf."""
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(REPO_ROOT / "deploy/all-in-one/config/supervisord.conf", encoding="utf-8")
    args = shlex.split(parser["program:worker"]["command"])
    return set(args[args.index("-Q") + 1].split(","))


@pytest.mark.unit
def test_ogni_task_pianificato_o_instradato_ha_una_coda_consumata_dal_worker():
    """Ogni task che beat schedula o che ha una route deve finire su una coda che
    il worker consuma, in entrambi i deployment (compose e all-in-one).

    Con `-Q delivery` soltanto, i job di manutenzione finivano sulla coda di default
    `celery` e non venivano mai eseguiti: nessun errore, solo job mai partiti.
    """
    consumed = {
        "docker-compose": _code_queues_from_compose(),
        "all-in-one": _code_queues_from_supervisord(),
    }
    task_names = set(EXPECTED_TASK_NAMES)
    task_names.update(entry["task"] for entry in celery_app.conf.beat_schedule.values())
    assert celery_app.conf.task_default_queue in consumed["docker-compose"]
    for name in sorted(task_names):
        queue = celery_app.amqp.router.route({}, name)["queue"].name
        for deployment, queues in consumed.items():
            assert queue in queues, f"{name} su coda '{queue}' non consumata in {deployment}"
