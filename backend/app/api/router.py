from fastapi import APIRouter

from app.api.routes import carparks, health, search

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(search.router)
api_router.include_router(carparks.router)

# Unversioned, for uptime checks
health_router = health.router
