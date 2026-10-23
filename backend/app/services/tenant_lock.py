"""Lock sulla riga del tenant per le scritture di impostazioni (cap per receiver,
impostazioni del tenant).

FOR NO KEY UPDATE, non FOR UPDATE: queste scritture non toccano colonne chiave,
e il FOR UPDATE pieno e' in conflitto con il FOR KEY SHARE che ogni INSERT su una
tabella figlia prende sulla riga del tenant (notifiche, consegne, token di
refresh). Con il lock pieno una modifica di un receiver bloccava l'ingestion e il
login di tutto il tenant per la durata della transazione. Con NO KEY UPDATE le
scritture di impostazioni restano serializzate fra loro e con il lock di quota
(che resta FOR UPDATE pieno, in services/quota.py), senza fermare gli INSERT.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant


async def lock_tenant_settings(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    """Prende il lock FOR NO KEY UPDATE sulla riga del tenant e la restituisce."""
    result = await session.execute(
        select(Tenant).where(Tenant.id == tenant_id).with_for_update(key_share=True)
    )
    return result.scalar_one()
