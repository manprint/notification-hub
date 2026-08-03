import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.db.types import Severity


class SeverityPresetRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    preset_id: uuid.UUID
    priority: int
    pattern: str
    case_insensitive: bool
    severity: Severity
    enabled: bool


class SeverityPresetRuleCreate(BaseModel):
    # Come per le regole dei receiver: priorita assente = accoda in fondo.
    priority: int | None = Field(default=None, ge=0)
    pattern: str = Field(min_length=1, max_length=200)
    case_insensitive: bool = True
    severity: Severity
    enabled: bool = True


class SeverityPresetRuleUpdate(BaseModel):
    priority: int | None = Field(default=None, ge=0)
    pattern: str | None = Field(default=None, min_length=1, max_length=200)
    case_insensitive: bool | None = None
    severity: Severity | None = None
    enabled: bool | None = None


class SeverityPresetRuleReorderIn(BaseModel):
    rule_ids: list[uuid.UUID] = Field(min_length=1)


class SeverityPresetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # Chiave del preset predefinito da cui nasce questa copia. None = preset
    # creato a mano nel tenant.
    builtin_key: str | None
    name: str
    description: str
    rules_count: int = 0
    receivers_count: int = 0


class SeverityPresetDetailOut(SeverityPresetOut):
    rules: list[SeverityPresetRuleOut] = []


class SeverityPresetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)


class SeverityPresetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class BuiltinPresetOut(BaseModel):
    """Voce del catalogo, indipendentemente dal fatto che sia gia installata."""

    key: str
    name: str
    description: str
    rules_count: int
    installed: bool


class SyncBuiltinPresetsOut(BaseModel):
    installed: list[str]
    already_present: list[str]


class ReceiverPresetOut(BaseModel):
    preset_id: uuid.UUID
    name: str
    description: str
    builtin_key: str | None
    position: int
    rules_count: int


class ReceiverPresetsIn(BaseModel):
    """Elenco completo dei preset applicati al receiver, nell'ordine voluto.

    Sostituisce l'associazione precedente: un elenco vuoto stacca tutto. Usare
    una sola operazione al posto di attach/detach separati rende impossibile
    ritrovarsi con posizioni scoperte o duplicate.
    """

    preset_ids: list[uuid.UUID] = Field(default_factory=list)


class SeverityChainItemOut(BaseModel):
    """Una riga della catena effettiva di un receiver, nell'ordine di valutazione."""

    position: int
    rule_id: uuid.UUID
    pattern: str
    case_insensitive: bool
    severity: Severity
    # "receiver" oppure "preset": dove va modificata questa regola.
    origin: str
    preset_id: uuid.UUID | None = None
    preset_name: str | None = None
