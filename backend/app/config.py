"""Settings, read from environment variables / backend/.env (see .env.example).
Database settings (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD) are read by app/db/session.py."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    cors_origins: list[str] = ["http://localhost:5500", "http://127.0.0.1:5500"]   # JSON list in .env

    # External APIs
    onemap_base_url: str = "https://www.onemap.gov.sg"
    onemap_email: str = ""
    onemap_password: str = ""
    onemap_api_token: str = ""          # alternative to email/password
    lta_base_url: str = "https://datamall2.mytransport.sg/ltaodataservice"
    lta_api_key: str = ""
    ura_api_key: str = ""               # URA Data Service AccessKey (emailed after registering)

    # Historical availability collector
    collector_enabled: bool = False     # True = run it inside the API process (only with ONE worker)
    collect_interval_minutes: int = 10

    # Search / ranking
    search_radius_m: float = 1000       # FR1.4: fixed 1 km
    max_walking_routes: int = 20        # OneMap routing calls per search (nearest carparks first)
