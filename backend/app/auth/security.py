from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from pwdlib import PasswordHash

from pydantic_settings import BaseSettings, SettingsConfigDict

class AuthSettings(BaseSettings):
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )


settings = AuthSettings()

password_hash = PasswordHash.recommended()

def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_expire_minutes
    )

    payload = {
        "sub": str(user_id),
        "exp": expire
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str):
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )

        user_id = payload.get("sub")

        if user_id is None:
            return None

        return int(user_id)

    except (JWTError, ValueError):
        return None