import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.db.types import OverrideMode, Severity


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1024)


class GroupUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1024)


class GroupOut(BaseModel):
    # from_attributes + model_validate(orm_object): i campi UUID vanno tipati
    # uuid.UUID, non str. Pydantic non converte un oggetto UUID in stringa
    # per un campo `str` durante la validazione da attributi (a differenza
    # della costruzione esplicita `GroupOut(id=str(...))`), e la validazione
    # fallisce a runtime (mai colto perche i vecchi test non passavano
    # dall'endpoint reale, vedi docs/REVIEW.md sezione 6).
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None


class GroupChannelBindingCreate(BaseModel):
    # uuid.UUID e non str: un id malformato deve dare 422 dalla validazione,
    # non una ValueError non gestita dentro l'endpoint (cioe un 500).
    channel_id: uuid.UUID
    min_severity: Severity
    enabled: bool = True


class GroupChannelBindingUpdate(BaseModel):
    min_severity: Severity | None = None
    enabled: bool | None = None


class GroupChannelBindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    group_id: uuid.UUID
    channel_id: uuid.UUID
    min_severity: Severity
    enabled: bool


class ReceiverChannelOverrideCreate(BaseModel):
    channel_id: uuid.UUID
    mode: OverrideMode
    min_severity: Severity | None = None


class ReceiverChannelOverrideUpdate(BaseModel):
    mode: OverrideMode | None = None
    min_severity: Severity | None = None


class ReceiverChannelOverrideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    receiver_id: uuid.UUID
    channel_id: uuid.UUID
    mode: OverrideMode
    min_severity: Severity | None
