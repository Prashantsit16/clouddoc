from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.database import SessionLocal
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import UserResponse


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED
)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db)
):
    existing_user = (
        db.query(User)
        .filter(User.email == request.email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered"
        )

    user = User(
        email=request.email,
        password_hash=hash_password(request.password)
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


@router.post(
    "/login",
    response_model=TokenResponse
)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    user = (
        db.query(User)
        .filter(User.email == request.email)
        .first()
    )

    if not user or not verify_password(
        request.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    access_token = create_access_token(user.id)

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }