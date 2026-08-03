"""Costruzione della catena di regole di un receiver.

Le regole che concorrono a decidere la severity di un messaggio stanno in due
posti: sul receiver (`severity_rules`) e nei preset applicati al receiver
(`severity_preset_rules`, attraverso `receiver_severity_presets`). Qui le due
liste diventano una sola sequenza ordinata, che e l'unica cosa che il motore di
risoluzione conosce.

ORDINE
------
1. le regole scritte sul receiver, per priorita crescente
2. le regole dei preset applicati, nell'ordine dei preset e, dentro ogni preset,
   per priorita crescente

Le regole del receiver vengono prima perche sono l'eccezione scritta apposta per
quel receiver: un preset e condiviso, e chi lo modifica non sa quali receiver lo
usano. Cosi una regola locale puo sempre correggere il preset senza doverlo
duplicare.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.severity_preset import (
    ReceiverSeverityPreset,
    SeverityPreset,
    SeverityPresetRule,
)
from app.models.severity_rule import SeverityRule
from app.services.severity import EvaluableRule


async def load_evaluation_chain(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    receiver_id: uuid.UUID,
) -> list[EvaluableRule]:
    """Le regole attive del receiver, nell'ordine esatto in cui verranno provate.

    `priority` viene riassegnata come posizione nella sequenza: da qui in avanti
    l'ordine e un fatto, non il risultato di un confronto fra numeri che vengono
    da tabelle diverse e possono coincidere.
    """
    own_result = await session.execute(
        select(SeverityRule)
        .where(
            SeverityRule.receiver_id == receiver_id,
            SeverityRule.tenant_id == tenant_id,
            SeverityRule.enabled.is_(True),
        )
        .order_by(SeverityRule.priority.asc(), SeverityRule.id.asc())
    )

    preset_result = await session.execute(
        select(SeverityPresetRule, SeverityPreset.id, SeverityPreset.name)
        .join(SeverityPreset, SeverityPreset.id == SeverityPresetRule.preset_id)
        .join(ReceiverSeverityPreset, ReceiverSeverityPreset.preset_id == SeverityPreset.id)
        .where(
            ReceiverSeverityPreset.receiver_id == receiver_id,
            ReceiverSeverityPreset.tenant_id == tenant_id,
            SeverityPresetRule.enabled.is_(True),
        )
        .order_by(
            ReceiverSeverityPreset.position.asc(),
            SeverityPresetRule.priority.asc(),
            SeverityPresetRule.id.asc(),
        )
    )

    chain: list[EvaluableRule] = []

    for rule in own_result.scalars().all():
        chain.append(
            EvaluableRule(
                pattern=rule.pattern,
                severity=rule.severity,
                priority=len(chain),
                case_insensitive=rule.case_insensitive,
                enabled=True,
                id=str(rule.id),
            )
        )

    for rule, preset_id, preset_name in preset_result.all():
        chain.append(
            EvaluableRule(
                pattern=rule.pattern,
                severity=rule.severity,
                priority=len(chain),
                case_insensitive=rule.case_insensitive,
                enabled=True,
                id=str(rule.id),
                preset_id=str(preset_id),
                preset_name=preset_name,
            )
        )

    return chain
