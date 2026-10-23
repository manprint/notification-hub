import logging
import uuid
from typing import Any

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _redact_secrets,  # type: ignore[list-item]
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(_livello_log(settings.log_level)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _livello_log(nome: str) -> int:
    # Nomi come in logging (INFO, WARNING, WARN...). Un valore sconosciuto blocca l'avvio:
    # ignorarlo in silenzio farebbe credere all'operatore che LOG_LEVEL funzioni.
    livelli = logging.getLevelNamesMapping()
    if nome.upper() not in livelli:
        raise ValueError(f"LOG_LEVEL non valido: {nome!r}")
    return livelli[nome.upper()]


def _redact_secrets(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    redact_keys = {"password", "token", "secret", "webhook", "authorization"}
    for key, value in list(event_dict.items()):
        if isinstance(value, str) and any(rk in key.lower() for rk in redact_keys):
            event_dict[key] = "[redacted]"
    return event_dict


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))

        token = structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["x-request-id"] = request_id

        structlog.contextvars.unbind_contextvars(*token)

        return response
