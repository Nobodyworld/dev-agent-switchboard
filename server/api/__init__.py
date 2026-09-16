"""Application factory for the Switchboard FastAPI service."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import JSONResponse, Response

from server.extensions import initialize_extensions
from server.middleware import RateLimitMiddleware
from server.observability import bootstrap_observability
from server.settings import get_rate_limit_settings

from .lifecycle import lifespan
from .routers import (
    agents,
    configuration,
    execution,
    files,
    github_execution,
    observability,
    plan,
    system_state,
    tasks,
    ui,
    worker_credentials,
    worker_execution,
)

DEFAULT_STATIC_DIR = Path(__file__).resolve().parents[2] / "web" / "static"


Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


@dataclass(slots=True)
class AppConfig:
    """Configuration values for :func:`create_app`."""

    title: str = "Switchboard"
    version: str = "0.1.0"
    cors_allow_origins: Iterable[str] = field(default_factory=lambda: ["*"])
    include_ui: bool = True
    static_directory: Path = DEFAULT_STATIC_DIR
    lifespan: Lifespan = lifespan


def create_app(config: AppConfig | None = None) -> FastAPI:
    """Create and configure a FastAPI application instance."""

    cfg = config or AppConfig()
    app = FastAPI(title=cfg.title, version=cfg.version, lifespan=cfg.lifespan)

    @app.middleware("http")
    async def enforce_worker_surface(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        credential_headers = request.headers.getlist(
            "Authorization"
        ) + request.headers.getlist("X-Switchboard-Admin-Token")
        if any(
            "swb_w1." in value.lower() for value in credential_headers
        ) and not request.url.path.startswith("/api/execution/worker/"):
            return JSONResponse(
                status_code=401, content={"detail": "worker_scope_denied"}
            )
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def bounded_worker_validation(
        request: Request, error: RequestValidationError
    ) -> Response:
        if request.url.path.startswith(
            ("/api/execution/worker/", "/api/execution/worker-credentials/")
        ):
            return JSONResponse(
                status_code=422, content={"detail": "invalid_worker_request"}
            )
        return await request_validation_exception_handler(request, error)

    bootstrap_observability(app)
    initialize_extensions(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cfg.cors_allow_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(
        RateLimitMiddleware,
        settings_provider=get_rate_limit_settings,
    )

    app.include_router(configuration.router)
    app.include_router(execution.router)
    app.include_router(worker_execution.router)
    app.include_router(worker_credentials.router)
    app.include_router(github_execution.router)
    app.include_router(observability.router)
    app.include_router(system_state.router)
    app.include_router(tasks.router)
    app.include_router(agents.router)
    app.include_router(plan.router)
    app.include_router(files.router)
    if cfg.include_ui:
        app.include_router(ui.router)
        if cfg.static_directory.exists():
            app.mount(
                "/static",
                StaticFiles(directory=str(cfg.static_directory)),
                name="static",
            )

    return app


__all__ = ["AppConfig", "create_app"]
