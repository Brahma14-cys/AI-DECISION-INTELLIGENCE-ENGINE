import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path
import shutil
import subprocess

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Depends
from urllib.parse import parse_qs, urlsplit

from app.api.auth import router as auth_router
from app.api.cases import router as cases_router
from app.api.analysis import router as analysis_router
from app.api.health import router as health_router
from app.api.knowledge_graph import router as knowledge_graph_router
from app.api.summaries import router as summaries_router
from app.api.legal_research import router as legal_research_router
from app.api.chat import router as chat_router
from app.api.deadlines import router as deadlines_router
from app.core.config import settings
from app.core.auth import require_advocate, require_same_origin
from app.core.encryption import encryption_key
from app.core.durable_worker import run_persistent_worker


def _validate_production_security() -> None:
    if settings.app_env.strip().lower() != "production":
        return
    if not encryption_key():
        raise RuntimeError("APP_ENCRYPTION_KEY is required in production to protect case data at rest.")
    if not settings.app_encryption_key_backup_confirmed:
        raise RuntimeError("Confirm a separate secure backup of APP_ENCRYPTION_KEY before production startup.")
    if not (settings.advocate_email and settings.advocate_password_hash and settings.session_secret):
        raise RuntimeError("The single-advocate account and session secret must be configured in production.")
    database_url = urlsplit(settings.database_url)
    if not database_url.scheme.startswith("postgresql"):
        raise RuntimeError("Production case data must use PostgreSQL with TLS enabled.")
    sslmode = parse_qs(database_url.query).get("sslmode", [""])[0].casefold()
    if sslmode != "verify-full":
        raise RuntimeError("Production PostgreSQL connections must use sslmode=verify-full.")
    scanner = settings.clamav_command
    if not scanner or not (shutil.which(scanner) or Path(scanner).is_file()):
        raise RuntimeError("A working ClamAV clamscan executable must be configured in production.")
    try:
        scanner_check = subprocess.run(
            [scanner, "--version"], check=False, capture_output=True, timeout=10, shell=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError("The configured ClamAV clamscan executable did not respond.") from error
    if scanner_check.returncode != 0:
        raise RuntimeError("The configured ClamAV clamscan executable did not pass its startup check.")
    if settings.knowledge_graph_enabled:
        if not (settings.neo4j_uri and settings.neo4j_user and settings.neo4j_password):
            raise RuntimeError("Neo4j URI and credentials are required when the knowledge graph is enabled.")
        if not settings.neo4j_uri.startswith(("neo4j+s://", "bolt+s://")):
            raise RuntimeError("Production Neo4j connections must use TLS with certificate verification.")
        if not settings.neo4j_storage_encryption_confirmed:
            raise RuntimeError("Confirm encrypted Neo4j storage before using the knowledge graph in production.")


_validate_production_security()


@asynccontextmanager
async def lifespan(_app):
    worker_task = None
    if settings.app_env.strip().lower() != "test":
        worker_task = asyncio.create_task(run_persistent_worker())
    try:
        yield
    finally:
        if worker_task is not None:
            worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await worker_task


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Case-centered legal decision intelligence for advocates.",
    docs_url="/docs" if settings.app_env.strip().lower() in {"development", "test"} else None,
    redoc_url=None,
    openapi_url=(
        f"{settings.api_v1_prefix}/openapi.json"
        if settings.app_env.strip().lower() in {"development", "test"}
        else None
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def add_private_response_headers(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response

app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(auth_router, prefix=settings.api_v1_prefix)
protected_dependencies = [Depends(require_same_origin), Depends(require_advocate)]
app.include_router(cases_router, prefix=settings.api_v1_prefix, dependencies=protected_dependencies)
app.include_router(analysis_router, prefix=settings.api_v1_prefix, dependencies=protected_dependencies)
app.include_router(knowledge_graph_router, prefix=settings.api_v1_prefix, dependencies=protected_dependencies)
app.include_router(summaries_router, prefix=settings.api_v1_prefix, dependencies=protected_dependencies)
app.include_router(legal_research_router, prefix=settings.api_v1_prefix, dependencies=protected_dependencies)
app.include_router(chat_router, prefix=settings.api_v1_prefix, dependencies=protected_dependencies)
app.include_router(deadlines_router, prefix=settings.api_v1_prefix, dependencies=protected_dependencies)
