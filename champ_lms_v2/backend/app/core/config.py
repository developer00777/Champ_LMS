from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    debug: bool = False
    secret_key: str = "dev-secret-key-change-in-prod"
    access_token_expire_minutes: int = 480

    # Database
    database_url: str = "postgresql+asyncpg://dev:dev@localhost/champlmsv2"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Bunny Storage
    bunny_account_api_key: str = ""
    bunny_storage_host: str = "storage.bunnycdn.com"
    bunny_storage_thumbs_zone: str = "champ-lms-thumbs"
    bunny_storage_thumbs_password: str = ""
    bunny_storage_frontend_zone: str = "champ-lms-frontend"
    bunny_storage_frontend_password: str = ""

    # Bunny CDN Pull Zone (serves thumbnails + static)
    bunny_cdn_hostname: str = ""
    bunny_cdn_token_secret: str = ""

    # Bunny Stream
    bunny_stream_api_key: str = ""
    bunny_stream_library_id: str = ""
    bunny_stream_cdn_hostname: str = ""
    bunny_stream_token_secret: str = ""
    bunny_stream_webhook_secret: str = ""

    # AI
    anthropic_api_key: str = ""

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

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
