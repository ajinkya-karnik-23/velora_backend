"""JWT token management and password hashing utilities."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings

# ---------------------------------------------------------------------------
# Password hashing (bcrypt, cost >= 12)
# ---------------------------------------------------------------------------

_BCRYPT_ROUNDS = 12


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt (cost 12)."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def create_access_token(
    data: dict,
    expires_delta: timedelta | None = None,
) -> str:
    """Create an access token.

    Payload includes: sub (user_id), roles, permissions, exp, iat, type.
    """
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode = {**data}
    # PyJWT >= 2.10 requires 'sub' to be a string
    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])
    payload = {
        **to_encode,
        "exp": expire,
        "iat": now,
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """Create a refresh token (longer-lived, type='refresh')."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {**data}
    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])
    payload = {
        **to_encode,
        "exp": expire,
        "iat": now,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    """Decode and verify a JWT token.

    Raises jwt.ExpiredSignatureError if expired.
    Raises jwt.InvalidTokenError for any other validation failure.
    """
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
