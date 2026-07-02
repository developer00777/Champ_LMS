from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from app.core.config import get_settings

_client: AsyncIOMotorClient | None = None


async def init_db() -> None:
    global _client
    settings = get_settings()
    _client = AsyncIOMotorClient(settings.mongodb_url)
    from app.models import DOCUMENT_MODELS

    await init_beanie(
        database=_client[settings.mongodb_db_name],
        document_models=DOCUMENT_MODELS,
    )


def close_db() -> None:
    global _client
    if _client:
        _client.close()
        _client = None
