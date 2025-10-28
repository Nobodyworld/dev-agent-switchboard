"""Application factory for the Switchboard FastAPI service."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server.extensions import initialize_extensions
from server.middleware import RateLimitMiddleware
from server.observability import bootstrap_observability
from server.settings import get_rate_limit_settings

from .lifecycle import lifespan
from .routers import (
    agents,
    configuration,
    files,
    observability,
    plan,
    system_state,
    tasks,
    ui,
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
