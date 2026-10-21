"""ASGI application. Uvicorn must bind 127.0.0.1 with one worker."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from veritas import __version__
from veritas.api.decisions import router as decision_router
from veritas.api.errors import (
    ApiError,
    api_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from veritas.api.middleware import CorrelationIdMiddleware
from veritas.api.routes import router
from veritas.api.scenarios import router as scenario_router
from veritas.api.settings import Settings
from veritas.api.verify import router as verify_router


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings if settings is not None else Settings.from_env()
    app = FastAPI(title="VERITAS", version=__version__)
    app.state.settings = resolved
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[resolved.cors_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(router)
    app.include_router(scenario_router)
    app.include_router(decision_router)
    app.include_router(verify_router)

    @app.get("/rulesets/current", include_in_schema=False)
    def root_current_ruleset() -> object:
        from veritas.api.routes import get_current_ruleset

        return get_current_ruleset()

    return app


app = create_app()
