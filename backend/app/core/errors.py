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
    "unsupported_media_type": "/problems/unsupported-media-type",
    "conflict": "/problems/conflict",
    "forbidden": "/problems/forbidden",
    "unauthorized": "/problems/unauthorized",
    "storage_unavailable": "/problems/storage-unavailable",
    "internal_error": "/problems/internal-error",
    "generic": "/problems/generic",
}

# Mappa status HTTP -> problem type per gli errori che non passano da Problem
# (HTTPException sollevate da FastAPI/Starlette stesse, non dall'applicazione).
STATUS_TO_PROBLEM_TYPE: dict[int, str] = {
    401: PROBLEM_TYPES["unauthorized"],
    403: PROBLEM_TYPES["forbidden"],
    404: PROBLEM_TYPES["not_found"],
    409: PROBLEM_TYPES["conflict"],
    413: PROBLEM_TYPES["payload_too_large"],
    415: PROBLEM_TYPES["unsupported_media_type"],
    422: PROBLEM_TYPES["validation_error"],
    429: PROBLEM_TYPES["rate_limited"],
    500: PROBLEM_TYPES["internal_error"],
}


def problem_type_for_status(status_code: int) -> str:
    return STATUS_TO_PROBLEM_TYPE.get(status_code, PROBLEM_TYPES["generic"])


def ingest_not_found() -> Problem:
    """Corpo unico per i tre casi che l'invariante I-2 impone indistinguibili:
    slug inesistente, receiver disabled, tenant suspended (spec 9.1)."""
    return Problem(
        status=status.HTTP_404_NOT_FOUND,
        type=PROBLEM_TYPES["not_found"],
        title="Not Found",
        detail="Receiver not found.",
    )
