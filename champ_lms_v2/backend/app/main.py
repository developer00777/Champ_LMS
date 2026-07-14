from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.db import init_db, close_db
from app.core.auth import seed_admin
from app.core.redis import get_redis, close_redis
from app.services.gamification_service import seed_gamification, rehydrate_leaderboards
from app.routers import auth, content, progress, gamification, admin, zoom, assessments, webhooks, learning_path, challenges, social

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await seed_admin()
    # * seed the badge catalog, then rebuild the Redis leaderboard from Mongo
    await seed_gamification()
    await rehydrate_leaderboards(await get_redis())
    # * Seed learning paths from existing department modules (idempotent)
    from seed_demo import seed_paths
    try:
        await seed_paths()
    except Exception:
        pass  # * non-critical: paths can be created via admin API later
    # * Seed team challenges (idempotent)
    from app.routers.challenges import seed_challenges
    try:
        await seed_challenges()
    except Exception:
        pass
    yield
    await close_redis()
    close_db()


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
app.include_router(learning_path.router)
app.include_router(challenges.router)
app.include_router(social.router)
app.include_router(webhooks.router)
# Bunny dashboard may be configured with /api prefix — support both paths
app.include_router(webhooks.router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
