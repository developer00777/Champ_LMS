from pydantic_settings import BaseSettings
from pydantic import model_validator
from functools import lru_cache


class Settings(BaseSettings):
    # App
    debug: bool = False
    secret_key: str = "dev-secret-key-change-in-prod"
    access_token_expire_minutes: int = 480

    # Database — set MONGODB_URL directly, or rely on Railway's MongoDB
    # plugin, which injects MONGO_URL instead (picked up as a fallback
    # below since the plugin's variable name isn't ours to control).
    mongodb_url: str = "mongodb://dev:dev@localhost:27017"
    mongodb_db_name: str = "champlmsv2"

    # Redis — Railway's Redis plugin injects REDIS_URL directly.
    redis_url: str = "redis://localhost:6379"

    # Bunny Storage (thumbnails only — frontend is hosted on Railway, not Bunny)
    bunny_account_api_key: str = ""
    bunny_storage_host: str = "storage.bunnycdn.com"
    bunny_storage_thumbs_zone: str = "champ-lms-thumbs"
    bunny_storage_thumbs_password: str = ""

    # Bunny CDN Pull Zone (serves thumbnails + static)
    bunny_cdn_hostname: str = ""
    bunny_cdn_token_secret: str = ""

    # Bunny Stream
    bunny_stream_api_key: str = ""
    bunny_stream_library_id: str = ""
    bunny_stream_cdn_hostname: str = ""
    bunny_stream_token_secret: str = ""
    bunny_stream_webhook_secret: str = ""

    # AI — OpenRouter (openrouter.ai/api/v1, OpenAI-compatible)
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemini-flash-1.5"  # cheap + fast; change freely in .env

    # Zoom
    zoom_webhook_secret: str = ""
    zoom_account_id: str = ""
    zoom_client_id: str = ""
    zoom_client_secret: str = ""

    # CORS
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    @model_validator(mode="before")
    @classmethod
    def _fallback_to_mongo_url(cls, values: dict) -> dict:
        """Railway's MongoDB plugin injects MONGO_URL, not MONGODB_URL."""
        if isinstance(values, dict) and not values.get("mongodb_url") and not values.get("MONGODB_URL"):
            import os

            fallback = os.environ.get("MONGO_URL")
            if fallback:
                values["mongodb_url"] = fallback
        return values

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
