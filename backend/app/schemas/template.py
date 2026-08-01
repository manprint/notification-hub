from pydantic import BaseModel, Field

from app.db.types import Severity


class NotificationTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1024)
    title_template: str = Field(min_length=1, max_length=500)
    body_template: str = Field(min_length=1, max_length=10000)
    default_severity: Severity = Field(default=Severity.INFO)
    variables: dict[str, str] = Field(default_factory=dict)


class NotificationTemplateUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1024)
    title_template: str | None = Field(None, min_length=1, max_length=500)
    body_template: str | None = Field(None, min_length=1, max_length=10000)
    default_severity: Severity | None = None
    is_active: bool | None = None
    variables: dict[str, str] | None = None


class NotificationTemplateOut(BaseModel):
    id: str
    name: str
    description: str | None
    title_template: str
    body_template: str
    default_severity: Severity
    is_active: bool
    variables: dict[str, str]


class TemplateRenderRequest(BaseModel):
    template_id: str
    variables: dict[str, str] = Field(default_factory=dict)


class TemplateRenderResponse(BaseModel):
    title: str
    body: str
    severity: Severity
