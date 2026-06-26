import httpx
from jose import jwk, jwt, JWTError
from jose.utils import base64url_decode
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import get_settings
from functools import lru_cache
import json

settings = get_settings()
bearer_scheme = HTTPBearer()

COGNITO_JWKS_URL = (
    f"https://cognito-idp.{settings.cognito_region}.amazonaws.com"
    f"/{settings.cognito_user_pool_id}/.well-known/jwks.json"
)


@lru_cache
def _get_jwks() -> dict:
    # Cached at startup — refreshed on process restart
    # In production use a background refresh task
    with httpx.Client() as client:
        resp = client.get(COGNITO_JWKS_URL, timeout=10)
        resp.raise_for_status()
        return resp.json()


def _find_key(kid: str) -> dict:
    jwks = _get_jwks()
    for key in jwks.get("keys", []):
        if key["kid"] == kid:
            return key
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Public key not found")


def verify_token(token: str) -> dict:
    try:
        headers = jwt.get_unverified_headers(token)
        kid = headers.get("kid")
        if not kid:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing kid in token")

        public_key = jwk.construct(_find_key(kid))
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=settings.cognito_client_id,
            options={"verify_exp": True},
        )
        return claims
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    return verify_token(credentials.credentials)


async def require_admin(claims: dict = Depends(get_current_user)) -> dict:
    groups = claims.get("cognito:groups", [])
    if "admins" not in groups:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return claims


# Local dev bypass — set COGNITO_USER_POOL_ID="" to use mock auth
async def get_current_user_dev(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    if not settings.cognito_user_pool_id:
        # Return a mock user for local development
        return {
            "sub": "dev-user-uuid",
            "email": "dev@championsgroup.com",
            "cognito:groups": ["admins"],
            "name": "Dev User",
        }
    return verify_token(credentials.credentials)
