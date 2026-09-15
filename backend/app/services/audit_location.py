"""Dove sta la risorsa di cui parla una riga di audit.

L'audit congela nome ed etichetta della risorsa, non la sua posizione: una
riga diceva "severity_rule / disco pieno" senza dire su quale receiver, e
"receiver / Backup notturno" senza dire di quale gruppo. Con tre gruppi che
hanno un receiver chiamato "Backup notturno" la tabella non risponde piu' alla
domanda per cui esiste.

La posizione si risolve **in lettura**, seguendo le chiavi esterne a partire da
`resource_id`: cosi' vale anche per gli eventi gia' scritti. Il prezzo e' che
una risorsa cancellata non ha piu' posizione (la riga di audit sopravvive alla
risorsa): in quel caso i campi restano nulli e l'interfaccia mostra un
trattino.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.binding import GroupChannelBinding, ReceiverChannelOverride
from app.models.group import Group
from app.models.notification import Notification
from app.models.receiver import Receiver
from app.models.severity_preset import ReceiverSeverityPreset
from app.models.severity_rule import SeverityRule

# Risorse che vivono dentro un receiver: la colonna porta gruppo e receiver.
# La chiave e' il `resource_type` scritto nell'audit, il valore la colonna da
# seguire per arrivare al receiver (None = `resource_id` e' gia' il receiver).
RECEIVER_SOURCES: dict[str, Any] = {
    "receiver": None,
    "notification": Notification,
    "severity_rule": SeverityRule,
    "receiver_severity_preset": ReceiverSeverityPreset,
    "receiver_channel_override": ReceiverChannelOverride,
}

# Risorse che vivono in un gruppo ma non in un receiver: la colonna porta il
# solo gruppo.
GROUP_SOURCES: dict[str, Any] = {
    "group": None,
    "group_channel_binding": GroupChannelBinding,
}

# Le liste di id vanno in un IN: un export puo' selezionare decine di migliaia
# di righe, e un IN con decine di migliaia di elementi e' un piano di query
# patologico. Si interroga a blocchi.
CHUNK = 1_000


@dataclass(frozen=True)
class Location:
    """Gruppo e receiver di una riga di audit. Tutto nullo = non risolvibile."""

    group_id: str | None = None
    group_name: str | None = None
    receiver_id: str | None = None
    receiver_name: str | None = None


EMPTY = Location()


def _chunks(values: Sequence[uuid.UUID]) -> Iterable[Sequence[uuid.UUID]]:
    for start in range(0, len(values), CHUNK):
        yield values[start : start + CHUNK]


def _as_uuid(value: Any) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError:
            return None
    return None


def _filter_scope(event: Any) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """Receiver e gruppo di un evento senza `resource_id`.

    Il `bulk-read` aggiorna N notifiche con un evento solo: non ha una risorsa
    singola, ma porta in `context.filters` l'ambito su cui ha agito, che e'
    esattamente cio' che serve sapere ("ha segnato lette tutte quelle di questo
    receiver").
    """
    context = getattr(event, "context", None)
    if not isinstance(context, dict):
        return None, None
    filters = context.get("filters")
    if not isinstance(filters, dict):
        return None, None
    return _as_uuid(filters.get("receiver_id")), _as_uuid(filters.get("group_id"))


async def _lookup(
    session: AsyncSession,
    model: Any,
    column: Any,
    ids: Sequence[uuid.UUID],
) -> dict[uuid.UUID, uuid.UUID]:
    """Da `id` della risorsa a `id` del suo contenitore (receiver o gruppo)."""
    found: dict[uuid.UUID, uuid.UUID] = {}
    for chunk in _chunks(ids):
        result = await session.execute(select(model.id, column).where(model.id.in_(chunk)))
        for row_id, parent_id in result:
            found[row_id] = parent_id
    return found


async def resolve_locations(
    session: AsyncSession, events: Sequence[Any]
) -> dict[uuid.UUID, Location]:
    """Posizione di ogni evento, per id dell'evento.

    Query in blocco, non una per riga: al massimo una per tipo di risorsa
    presente nella pagina, piu' due (receiver e gruppi).
    """
    if not events:
        return {}

    # 1. Da ogni evento all'id da seguire, per tipo di risorsa.
    da_risolvere: dict[str, set[uuid.UUID]] = {}
    receiver_diretti: dict[uuid.UUID, uuid.UUID] = {}
    gruppo_diretti: dict[uuid.UUID, uuid.UUID] = {}
    indiretti: dict[uuid.UUID, tuple[str, uuid.UUID]] = {}

    for event in events:
        resource_id = _as_uuid(getattr(event, "resource_id", None))
        resource_type = getattr(event, "resource_type", None)
        if resource_id is None:
            # Nessuna risorsa singola: resta l'ambito dei filtri (bulk-read).
            receiver_id, group_id = _filter_scope(event)
            if receiver_id is not None:
                receiver_diretti[event.id] = receiver_id
            elif group_id is not None:
                gruppo_diretti[event.id] = group_id
            continue
        if resource_type in RECEIVER_SOURCES:
            model = RECEIVER_SOURCES[resource_type]
            if model is None:
                receiver_diretti[event.id] = resource_id
            else:
                indiretti[event.id] = (resource_type, resource_id)
                da_risolvere.setdefault(resource_type, set()).add(resource_id)
        elif resource_type in GROUP_SOURCES:
            model = GROUP_SOURCES[resource_type]
            if model is None:
                gruppo_diretti[event.id] = resource_id
            else:
                indiretti[event.id] = (resource_type, resource_id)
                da_risolvere.setdefault(resource_type, set()).add(resource_id)

    # 2. Un salto per arrivare al contenitore (notifica -> receiver, binding ->
    #    gruppo), una query per tipo.
    padri: dict[str, dict[uuid.UUID, uuid.UUID]] = {}
    for resource_type, ids in da_risolvere.items():
        if resource_type in RECEIVER_SOURCES:
            model = RECEIVER_SOURCES[resource_type]
            padri[resource_type] = await _lookup(session, model, model.receiver_id, sorted(ids))
        else:
            model = GROUP_SOURCES[resource_type]
            padri[resource_type] = await _lookup(session, model, model.group_id, sorted(ids))

    for event_id, (resource_type, resource_id) in indiretti.items():
        parent = padri.get(resource_type, {}).get(resource_id)
        if parent is None:
            continue
        if resource_type in RECEIVER_SOURCES:
            receiver_diretti[event_id] = parent
        else:
            gruppo_diretti[event_id] = parent

    # 3. Nomi: i receiver (che portano anche il proprio gruppo) e i gruppi.
    receivers: dict[uuid.UUID, tuple[str, uuid.UUID]] = {}
    for chunk in _chunks(sorted(set(receiver_diretti.values()))):
        result = await session.execute(
            select(Receiver.id, Receiver.name, Receiver.group_id).where(Receiver.id.in_(chunk))
        )
        for receiver_id, name, group_id in result:
            receivers[receiver_id] = (name, group_id)

    group_ids = set(gruppo_diretti.values()) | {gid for _, gid in receivers.values()}
    gruppi: dict[uuid.UUID, str] = {}
    for chunk in _chunks(sorted(group_ids)):
        result = await session.execute(select(Group.id, Group.name).where(Group.id.in_(chunk)))
        for group_id, name in result:
            gruppi[group_id] = name

    # 4. Una Location per evento.
    posizioni: dict[uuid.UUID, Location] = {}
    for event_id, receiver_id in receiver_diretti.items():
        trovato = receivers.get(receiver_id)
        if trovato is None:
            # Receiver cancellato: la riga di audit resta, la posizione no.
            continue
        name, group_id = trovato
        posizioni[event_id] = Location(
            group_id=str(group_id),
            group_name=gruppi.get(group_id),
            receiver_id=str(receiver_id),
            receiver_name=name,
        )
    for event_id, group_id in gruppo_diretti.items():
        name = gruppi.get(group_id)
        if name is None:
            continue
        posizioni[event_id] = Location(group_id=str(group_id), group_name=name)

    return posizioni
