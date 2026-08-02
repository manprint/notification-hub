from pydantic import BaseModel


class IngestResponse(BaseModel):
    """Spec 9.1: {"id": "...", "severity": "error", "forwarded_to": 2}.

    severity_source non e nella tabella della spec 9.1 ma e citato in sezione 12
    passo 8 dello scenario di riferimento ed e utile in diagnostica: aggiunto
    come campo extra, non sostituisce nessuno dei tre richiesti.
    """

    id: str
    severity: str
    severity_source: str
    forwarded_to: int
    storage_backend: str
