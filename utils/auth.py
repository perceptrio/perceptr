from datetime import UTC, datetime, timedelta

from common.types import CreateTokenPayload
from core.constants import APIPath
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from settings import settings
import hashlib
import bcrypt

_BCRYPT_ROUNDS = 12


SECRET_KEY = settings.SECRET_KEY
REFRESH_SECRET_KEY = settings.REFRESH_SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = settings.REFRESH_TOKEN_EXPIRE_DAYS

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{APIPath.V1}/orgs/token")


def _sha256_hexdigest_bytes(password: str) -> bytes:
    return hashlib.sha256(password.encode()).hexdigest().encode()


def get_password_hash(password: str) -> str:
    """Hash password using bcrypt of SHA256-hexdigest(password).

    Returns a standard bcrypt hash string (e.g., "$2b$12$...").
    """
    prehashed = _sha256_hexdigest_bytes(password)
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(prehashed, salt)

    return hashed.decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against stored hash.

    Tries legacy prehashed mode first (sha256-hexdigest -> bcrypt). If that fails, it
    falls back to checking plain bcrypt (no pre-hash). Any ValueError from bcrypt
    (e.g., due to >72 byte inputs in plain mode) is treated as a failed check.
    """
    hp_bytes = hashed_password.encode()

    # 1) Preferred / legacy-compatible path: sha256-hexdigest -> bcrypt
    prehashed = _sha256_hexdigest_bytes(plain_password)
    if bcrypt.checkpw(prehashed, hp_bytes):
        return True

    # 2) Fallback: plain -> bcrypt (only if some old records used plain bcrypt)
    try:

        return bcrypt.checkpw(plain_password.encode(), hp_bytes)

    except ValueError:
        # bcrypt v5 raises if input >72 bytes (instead of silently truncating)

        return False


def create_access_token(data: CreateTokenPayload) -> str:
    to_encode = data.model_dump()
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: CreateTokenPayload) -> str:
    to_encode = data.model_dump()
    expire = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, REFRESH_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def validate_org_token(
    token: str, secret_key: str = SECRET_KEY, algorithm: str = ALGORITHM
) -> int:
    payload = jwt.decode(token, secret_key, algorithms=[algorithm])
    org_id = payload.get("org_id")
    if not org_id:
        raise ValueError("Invalid token: org_id missing")
    return org_id
