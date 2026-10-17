import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import auth
from app.core.config import settings
from app.core.database import get_db
from app.core.encryption import encryption_key
from app.db.models import AdvocateAccount


router = APIRouter(prefix="/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=1024)


class AdvocateSession(BaseModel):
    email: str


_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _encryption_key_is_ready() -> bool:
    try:
        return encryption_key() is not None
    except RuntimeError:
        return False


@router.get("/setup-status")
def setup_status(db: Session = Depends(get_db)) -> dict[str, object]:
    credentials = auth.get_advocate_credentials(db)
    development_bootstrap_allowed = settings.app_env.strip().lower() in {"development", "test"}
    encryption_ready = _encryption_key_is_ready()
    available = credentials is None and development_bootstrap_allowed and encryption_ready
    if available:
        message = "Create the one advocate account for this installation."
    elif credentials is not None:
        message = "The single advocate account is already configured. Sign in to continue."
    elif development_bootstrap_allowed and not encryption_ready:
        message = "Browser signup requires APP_ENCRYPTION_KEY. Configure it before creating an account."
    else:
        message = "Browser-based setup is disabled in this environment. Ask the administrator to configure advocate credentials."
    return {
        "configured": credentials is not None,
        "signup_available": available,
        "mode": "single_advocate",
        "message": message,
    }


@router.post(
    "/register",
    response_model=AdvocateSession,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth.require_same_origin)],
)
def register(payload: SignupRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> AdvocateSession:
    if settings.app_env.strip().lower() not in {"development", "test"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Browser-based signup is disabled in this environment.")
    client_host = request.client.host if request.client else "unknown"
    if settings.app_env.strip().lower() != "test" and client_host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="First-run signup is only available from this machine.")
    if not _EMAIL_PATTERN.fullmatch(payload.email):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enter a valid email address.")
    if not _encryption_key_is_ready():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Configure APP_ENCRYPTION_KEY before creating an advocate account.")
    if auth.get_advocate_credentials(db) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The single advocate account is already configured. Sign in instead.")
    try:
        password_hash = auth.hash_password(payload.password)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from None
    session_secret = secrets.token_urlsafe(48)
    account = AdvocateAccount(
        id=1,
        email=payload.email.strip().lower(),
        password_hash=password_hash,
        session_secret=session_secret,
    )
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The advocate account was already created. Sign in instead.") from None
    db.refresh(account)
    auth.set_session_cookie(response, account.email, session_secret)
    return AdvocateSession(email=account.email)


@router.post("/login", response_model=AdvocateSession, dependencies=[Depends(auth.require_same_origin)])
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> AdvocateSession:
    credentials = auth.get_advocate_credentials(db)
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Advocate sign-in is not configured. Follow the setup steps in README.md.",
        )
    client_key = request.client.host if request.client else "unknown"
    auth.check_login_rate_limit(client_key)
    if not _EMAIL_PATTERN.fullmatch(payload.email):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enter a valid email address.")
    expected_email = credentials.email
    password_ok = auth.verify_password(payload.password, credentials.password_hash)
    email_ok = payload.email.casefold() == expected_email.casefold()
    if not (password_ok and email_ok):
        auth.record_failed_login(client_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect.",
            headers={"WWW-Authenticate": "Session"},
        )
    auth.clear_failed_logins(client_key)
    auth.set_session_cookie(response, expected_email, credentials.session_secret)
    return AdvocateSession(email=expected_email)


@router.get("/me", response_model=AdvocateSession)
def get_session(email: str = Depends(auth.require_advocate)) -> AdvocateSession:
    return AdvocateSession(email=email)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(auth.require_same_origin), Depends(auth.require_advocate)],
)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    auth.revoke_session(request.cookies.get(auth.SESSION_COOKIE), db)
    auth.clear_session_cookie(response)
