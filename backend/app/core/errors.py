from typing import Any

from fastapi import status
from starlette.responses import JSONResponse


class Problem(Exception):
    def __init__(
        self,
        status: int,
        type: str,
        title: str,
        detail: str = "",
        extra: dict[str, Any] | None = None,
    ):
        self.status = status
        self.type = type
        self.title = title
        self.detail = detail
        self.extra = extra or {}
        super().__init__(detail)


def problem_response(p: Problem) -> JSONResponse:
    body = {
        "type": p.type,
        "title": p.title,
        "status": p.status,
        "detail": p.detail,
        **p.extra,
    }
    return JSONResponse(status_code=p.status, content=body)


PROBLEM_TYPES = {
    "not_found": "/problems/not-found",
    "validation_error": "/problems/validation-error",
    "last_owner": "/problems/last-owner",
    "quota_exceeded": "/problems/quota-exceeded",
    "rate_limited": "/problems/rate-limited",
    "payload_too_large": "/problems/payload-too-large",
    "conflict": "/problems/conflict",
    "forbidden": "/problems/forbidden",
    "unauthorized": "/problems/unauthorized",
    "storage_unavailable": "/problems/storage-unavailable",
}

INGEST_NOT_FOUND_BODY = {
    "type": PROBLEM_TYPES["not_found"],
    "title": "Not Found",
    "status": status.HTTP_404_NOT_FOUND,
    "detail": "Receiver not found.",
}
