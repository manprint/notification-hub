from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException

from app.core.config import get_settings
from app.core.errors import (
    PROBLEM_TYPES,
    Problem,
    jsonable_validation_errors,
    problem_response,
    problem_type_for_status,
)
from app.core.logging import RequestIdMiddleware, configure_logging, get_logger


def create_app() -> FastAPI:
    configure_logging()
    logger = get_logger(__name__)
    settings = get_settings()

    app = FastAPI(title="NotifyHub", version="0.1.0", docs_url="/docs")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Il nome del file dello script wrapper viaggia qui: senza esporlo, una
        # SPA servita da un'origine diversa dall'API scaricherebbe uno script
        # senza nome.
        expose_headers=["Content-Disposition"],
    )
    app.add_middleware(RequestIdMiddleware)

    @app.exception_handler(Problem)
    async def problem_handler(request: Request, exc: Problem) -> JSONResponse:
        return problem_response(exc)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        p = Problem(
            status=status.HTTP_422_UNPROCESSABLE_CONTENT,
            type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail="Request validation failed.",
            extra={"errors": jsonable_validation_errors(exc.errors())},
        )
        return problem_response(p)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        p = Problem(
            status=exc.status_code,
            type=problem_type_for_status(exc.status_code),
            title=exc.detail or "HTTP Error",
            detail=exc.detail or "",
        )
        return problem_response(p)

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        """Rete di sicurezza: una violazione di vincolo (unicita, chiave
        esterna) e un conflitto sui dati della richiesta, non un guasto del
        server. Gli endpoint la prevengono a monte, ma senza questo handler
        ogni caso non previsto uscirebbe come 500 opaco."""
        logger.warning("integrity_error", error=str(exc.orig))
        p = Problem(
            status=status.HTTP_409_CONFLICT,
            type=PROBLEM_TYPES["conflict"],
            title="Conflict",
            detail="The request conflicts with the current state of the data.",
        )
        return problem_response(p)

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", exc_info=exc)
        p = Problem(
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            type=PROBLEM_TYPES["internal_error"],
            title="Internal Server Error",
            detail="An internal error occurred.",
        )
        return problem_response(p)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        from app.core.readiness import check_readiness

        checks = await check_readiness()
        ready = all(checks.values())
        return JSONResponse(
            status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"ready": ready, "checks": checks},
        )

    from app.api import ingest
    from app.api.v1 import (
        audit,
        auth,
        channels,
        groups,
        notifications,
        presets,
        receivers,
        stats,
        tenant,
        users,
    )

    app.include_router(ingest.router)
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(auth.invitations_router, prefix="/api/v1")
    app.include_router(users.router, prefix="/api/v1")
    app.include_router(channels.router, prefix="/api/v1")
    app.include_router(groups.router, prefix="/api/v1")
    app.include_router(receivers.router, prefix="/api/v1")
    app.include_router(presets.router, prefix="/api/v1")
    app.include_router(tenant.router, prefix="/api/v1")
    app.include_router(notifications.router, prefix="/api/v1")
    app.include_router(stats.router, prefix="/api/v1")
    app.include_router(audit.router, prefix="/api/v1")

    # ROUTERS: i router delle fasi successive si registrano qui sopra

    return app


app = create_app()
