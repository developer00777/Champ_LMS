from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.db import engine, Base
from app.core.redis import close_redis
from app.routers import auth, content, progress, gamification, admin, zoom, assessments, webhooks

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (use Alembic in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await close_redis()


app = FastAPI(
    title="Champ LMS v2",
    description="Netflix-style company learning platform — Bunny CDN powered",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(content.router)
app.include_router(progress.router)
app.include_router(gamification.router)
app.include_router(admin.router)
app.include_router(zoom.router)
app.include_router(assessments.router)
app.include_router(webhooks.router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
