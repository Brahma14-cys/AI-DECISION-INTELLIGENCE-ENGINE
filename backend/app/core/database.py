from collections.abc import Generator
from uuid import UUID

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.models import Case


engine: Engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def lock_case_for_update(db: Session, case_id: UUID) -> Case | None:
    """Lock a case row across concurrent queueing and deletion operations."""
    if engine.dialect.name == "sqlite":
        # SQLite ignores SELECT FOR UPDATE. Acquire its write reservation before
        # reading the case so other writers serialize until this transaction ends.
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    return db.scalar(select(Case).where(Case.id == case_id).with_for_update())


def is_database_ready() -> bool:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
