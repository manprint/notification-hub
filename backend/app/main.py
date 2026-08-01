from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.core.errors import PROBLEM_TYPES, Problem, problem_response
from app.core.logging import RequestIdMiddleware, configure_logging, get_logger


def create_app() -> FastAPI:
    configure_logging()
    logger = get_logger(__name__)

    app = FastAPI(title="NotifyHub", version="0.1.0", docs_url="/docs")

    app.add_middleware(RequestIdMiddleware)

    @app.exception_handler(Problem)
    async def problem_handler(request: Request, exc: Problem) -> JSONResponse:
        return problem_response(exc)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        p = Problem(
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            type=PROBLEM_TYPES["validation_error"],
            title="Validation Error",
            detail="Request validation failed.",
            extra={"errors": exc.errors()},
        )
        return problem_response(p)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        p = Problem(
            status=exc.status_code,
            type=PROBLEM_TYPES.get("not_found", "/problems/generic"),
            title=exc.detail or "HTTP Error",
            detail=exc.detail or "",
        )
        return problem_response(p)

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", exc_info=exc)
        p = Problem(
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            type="/problems/internal-error",
            title="Internal Server Error",
            detail="An internal error occurred.",
        )
        return problem_response(p)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    from app.api.v1 import auth, delivery, groups, ingestion, notifications, search, users

    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(users.router, prefix="/api/v1")
    app.include_router(ingestion.router, prefix="/api/v1")
    app.include_router(delivery.router, prefix="/api/v1")
    app.include_router(groups.router, prefix="/api/v1")
    app.include_router(notifications.router, prefix="/api/v1")
    app.include_router(search.router, prefix="/api/v1")

    # ROUTERS: i router delle fasi successive si registrano qui sopra

    return app
