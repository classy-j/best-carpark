"""FastAPI entry point.  Run from backend/:   uvicorn app.main:app --reload"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router, health_router
from app.collectors.scheduler import build_scheduler
from app.dependencies import build_collector, get_settings
from app.exceptions import AddressNotFoundError, ApiClientError, MultipleDestinationsError

log = logging.getLogger(__name__)


class AppBootstrap:
    """«startup» class: configures the app and starts the background collector if enabled."""

    def __init__(self):
        self.settings = get_settings()
        self._scheduler = None

    def start(self) -> None:
        if self.settings.collector_enabled:    # or run app.collectors.run_collector separately
            self._scheduler = build_scheduler(build_collector())
            self._scheduler.start()
            log.info("Collector started inside the API process")

    def stop(self) -> None:
        if self._scheduler:
            self._scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    bootstrap = AppBootstrap()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        bootstrap.start()
        yield
        bootstrap.stop()

    app = FastAPI(title="Best Carpark API", version="0.2.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=bootstrap.settings.cors_origins,
                       allow_methods=["*"], allow_headers=["*"])
    app.include_router(health_router)
    app.include_router(api_router)

    @app.exception_handler(AddressNotFoundError)
    async def address_not_found(_: Request, exc: AddressNotFoundError):        # UC-12
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(MultipleDestinationsError)
    async def multiple_destinations(_: Request, exc: MultipleDestinationsError):  # UC-01 AF1
        return JSONResponse(status_code=409, content={
            "detail": "Several places match the destination. Pick one.",
            "matches": [m.model_dump() for m in exc.matches]})

    @app.exception_handler(ApiClientError)
    async def upstream_failure(_: Request, exc: ApiClientError):
        log.error("Upstream API failure: %s", exc)
        return JSONResponse(status_code=502, content={"detail": "An external data service is unavailable."})

    return app


app = create_app()
