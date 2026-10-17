"""Single-advocate authentication and signed browser sessions."""

from collections import defaultdict, deque
import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from datetime import UTC, datetime
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.db.models import AdvocateAccount, RevokedSession


SESSION_COOKIE = "legal_engine_session"
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_failed_login_times: dict[str, deque[float]] = defaultdict(deque)
_failed_login_lock = threading.Lock()


@dataclass(frozen=True)
class AdvocateCredentials:
    email: str
    password_hash: str
    session_secret: str


def get_advocate_credentials(db: Session | None = None) -> AdvocateCredentials | None:
    """Prefer explicit server configuration; otherwise read the singleton signup."""
    if (
        settings.advocate_email
        and settings.advocate_password_hash
        and settings.session_secret
        and len(settings.session_secret.encode("utf-8")) >= 32
    ):
        return AdvocateCredentials(
            email=settings.advocate_email,
            password_hash=settings.advocate_password_hash,
            session_secret=settings.session_secret,
        )
    if db is None:
        return None
    account = db.get(AdvocateAccount, 1)
    if account is None or len(account.session_secret.encode("utf-8")) < 32:
        return None
    return AdvocateCredentials(
        email=account.email,
        password_hash=account.password_hash,
        session_secret=account.session_secret,
    )


def auth_is_configured(db: Session | None = None) -> bool:
    return get_advocate_credentials(db) is not None


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Choose a password with at least 12 characters.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N,
        _SCRYPT_R,
        _SCRYPT_P,
        _b64encode(salt),
        _b64encode(digest),
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, n, r, p, salt_text, digest_text = encoded_hash.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = _b64decode(salt_text)
        expected = _b64decode(digest_text)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
            maxmem=128 * 1024 * 1024,
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, MemoryError):
        return False


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _sign(payload: str, session_secret: str | None = None) -> str:
    secret = session_secret or settings.session_secret
    if not secret:
        raise RuntimeError("A session signing secret is not configured.")
    signature = hmac.new(
        secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256
    ).digest()
    return f"{payload}.{_b64encode(signature)}"


def create_session(email: str, now: int | None = None, session_secret: str | None = None) -> str:
    issued_at = now if now is not None else int(time.time())
    payload = _b64encode(
        json.dumps(
            {"sub": email, "exp": issued_at + settings.session_ttl_seconds, "jti": secrets.token_urlsafe(12)},
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return _sign(payload, session_secret)


def _verified_session(
    token: str | None,
    now: int | None = None,
    *,
    credentials: AdvocateCredentials | None = None,
) -> tuple[str, str, int] | None:
    expected_credentials = credentials or get_advocate_credentials()
    if not token or expected_credentials is None:
        return None
    try:
        payload, signature = token.rsplit(".", 1)
        expected = _sign(payload, expected_credentials.session_secret).rsplit(".", 1)[1]
        if not hmac.compare_digest(signature, expected):
            return None
        data = json.loads(_b64decode(payload))
        current_time = now if now is not None else int(time.time())
        if int(data["exp"]) <= current_time:
            return None
        email = data["sub"]
        jti = data["jti"]
        if not isinstance(email, str) or email.casefold() != expected_credentials.email.casefold():
            return None
        if not isinstance(jti, str) or not jti:
            return None
        return expected_credentials.email, jti, int(data["exp"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def session_email(token: str | None, now: int | None = None) -> str | None:
    verified = _verified_session(token, now)
    return verified[0] if verified else None


def check_login_rate_limit(client_key: str, now: float | None = None) -> None:
    current = now if now is not None else time.monotonic()
    cutoff = current - settings.login_window_seconds
    with _failed_login_lock:
        attempts = _failed_login_times[client_key]
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if len(attempts) >= settings.login_attempt_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many sign-in attempts. Wait before trying again.",
                headers={"Retry-After": str(settings.login_window_seconds)},
            )


def record_failed_login(client_key: str, now: float | None = None) -> None:
    with _failed_login_lock:
        _failed_login_times[client_key].append(now if now is not None else time.monotonic())


def clear_failed_logins(client_key: str) -> None:
    with _failed_login_lock:
        _failed_login_times.pop(client_key, None)


def require_same_origin(request: Request) -> None:
    if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return
    origin = request.headers.get("origin")
    fetch_site = request.headers.get("sec-fetch-site", "").lower()
    if origin not in settings.allowed_origins or fetch_site == "cross-site":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request origin is not allowed.",
        )


def require_advocate(request: Request, db: Session = Depends(get_db)) -> str:
    credentials = get_advocate_credentials(db)
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Advocate sign-in is not configured. Set the three ADVOCATE_* session values in backend/.env.",
        )
    verified = _verified_session(request.cookies.get(SESSION_COOKIE), credentials=credentials)
    if verified is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to access this case workspace.",
        )
    email, jti, _expiry = verified
    jti_hash = hashlib.sha256(jti.encode("utf-8")).hexdigest()
    if db.get(RevokedSession, jti_hash) is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This advocate session was signed out. Sign in again.")
    return email


def revoke_session(token: str | None, db: Session) -> None:
    verified = _verified_session(token, credentials=get_advocate_credentials(db))
    if verified is None:
        return
    _email, jti, expiry = verified
    db.execute(delete(RevokedSession).where(RevokedSession.expires_at <= datetime.now(UTC)))
    db.merge(RevokedSession(
        jti_hash=hashlib.sha256(jti.encode("utf-8")).hexdigest(),
        expires_at=datetime.fromtimestamp(expiry, UTC),
    ))
    db.commit()


def set_session_cookie(response: Response, email: str, session_secret: str | None = None) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_session(email, session_secret=session_secret),
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.app_env.strip().lower() not in {"development", "test"},
        samesite="strict",
        path=settings.api_v1_prefix,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE,
        path=settings.api_v1_prefix,
        httponly=True,
        secure=settings.app_env.strip().lower() not in {"development", "test"},
        samesite="strict",
    )
