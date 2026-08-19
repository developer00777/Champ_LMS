from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from app.core.auth import hash_password, verify_password, create_access_token, get_current_user
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    department: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    must_change_password: bool = False


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str | None
    role: str
    department: str | None
    team: str | None = None
    must_change_password: bool = False
    points: int
    xp: int
    level: int
    streak_days: int

    class Config:
        from_attributes = True


@router.post("/register", status_code=403, include_in_schema=False)
async def register(body: RegisterRequest):
    """
    Public sign-up is disabled: Champ LMS is internal, and accounts are
    provisioned by an admin via POST /admin/employees.

    The route is kept (rather than deleted) so an old client or a bookmarked
    form gets a clear explanation instead of a bare 404 that looks like an
    outage.
    """
    raise HTTPException(
        status_code=403,
        detail=(
            "Self-registration is disabled. Ask an administrator to create "
            "your account."
        ),
    )


@router.post("/token", response_model=TokenResponse)
async def login(form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user = await User.find_one(User.email == form.username)
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated. Contact an administrator.",
        )
    token = create_access_token({"sub": user.id})
    # * must_change_password lets the client route straight to the change form
    # * after a first sign-in with an admin-issued password.
    return {"access_token": token, "must_change_password": user.must_change_password}


@router.get("/me", response_model=UserOut)
async def me(user: Annotated[User, Depends(get_current_user)]):
    return user
