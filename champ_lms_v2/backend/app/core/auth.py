"""
Self-managed JWT auth (no Cognito).
Tokens are HS256, signed with SECRET_KEY.
"""
from datetime import datetime, timedelta, timezone
from typing import Annotated
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from app.core.config import get_settings
from app.models.user import User

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

ALGORITHM = "HS256"


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    return jwt.encode(
        {**data, "exp": expire},
        settings.secret_key,
        algorithm=ALGORITHM,
    )


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    user = await User.get(user_id)
    if user is None:
        raise credentials_exc
    return user


async def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role not in ("admin", "ld_lead"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def seed_admin() -> None:
    """
    Create (or promote) the hardcoded admin account from ADMIN_EMAIL/
    ADMIN_PASSWORD env vars. Idempotent — safe to run on every startup.
    This is the only way to create an admin; POST /auth/register always
    creates role="learner".
    """
    if not settings.admin_email or not settings.admin_password:
        return

    user = await User.find_one(User.email == settings.admin_email)
    if user:
        if user.role != "admin":
            user.role = "admin"
            await user.save()
        return

    await User(
        email=settings.admin_email,
        full_name="Admin",
        hashed_password=hash_password(settings.admin_password),
        role="admin",
    ).insert()
