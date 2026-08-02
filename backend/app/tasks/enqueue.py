"""Astrazione iniettabile per l'accodamento dei task Celery (D7 del piano).

Isolare l'enqueue dietro una funzione sostituibile rende verificabile con un
test unitario, senza broker, il rispetto dell'ordine commit-poi-enqueue
(spec 8.3): il test sostituisce _enqueue_fn con un raccoglitore in memoria e
verifica che venga chiamato solo dopo il commit della transazione.
"""

from collections.abc import Callable

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

EnqueueFn = Callable[[str, str], None]


def _default_enqueue(delivery_id: str, tenant_id: str) -> None:
    from app.tasks.delivery import dispatch_delivery

    dispatch_delivery.delay(delivery_id, tenant_id)


_enqueue_fn: EnqueueFn = _default_enqueue


def enqueue_delivery(delivery_id: str, tenant_id: str) -> None:
    _enqueue_fn(delivery_id, tenant_id)


def set_enqueue_function(fn: EnqueueFn) -> None:
    global _enqueue_fn
    _enqueue_fn = fn


def reset_enqueue_function() -> None:
    global _enqueue_fn
    _enqueue_fn = _default_enqueue


def register_after_commit_enqueue(session: AsyncSession, pending: list[tuple[str, str]]) -> None:
    """Registra l'accodamento su un hook 'after_commit' della sessione (spec
    8.3): chiamare dispatch_delivery.delay() dentro la transazione e la fonte
    di bug piu comune del pattern outbox, perche un worker veloce potrebbe
    prendere il task e cercare una riga che nessuno ha ancora committato.

    Se il processo muore fra commit ed enqueue il task si perde: la riga
    resta `pending` e la ripesca reconcile_deliveries entro 5 minuti (spec
    8.3). Questo hook e l'ottimizzazione di latenza, non la garanzia.
    """
    if not pending:
        return

    @event.listens_for(session.sync_session, "after_commit")
    def _enqueue(_: object) -> None:
        for delivery_id, tenant_id in pending:
            enqueue_delivery(delivery_id, tenant_id)
