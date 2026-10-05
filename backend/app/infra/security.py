from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.infra.settings import get_settings

JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=get_settings().bcrypt_rounds)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(user_id: int, rol: str, now: datetime | None = None) -> str:
    """La caducidad del token es un asunto técnico: usa la hora real, no el reloj del dominio."""
    settings = get_settings()
    now = now or datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "rol": rol, "iat": now, "exp": now + timedelta(minutes=settings.jwt_expire_minutes)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """Devuelve el id del usuario, o None si el token es inválido o expiró."""
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
