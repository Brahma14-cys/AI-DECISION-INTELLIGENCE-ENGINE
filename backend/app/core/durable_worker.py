"""Persistent status-backed task queue for the single-advocate deployment."""

import asyncio
from datetime import UTC, datetime
import hashlib
import logging
import os
from pathlib import Path
import tempfile
from time import perf_counter
from threading import Lock
from typing import Any

from sqlalchemy import select, text, update

from app.core.database import SessionLocal, engine
from app.db.models import CaseAnalysisRun, CaseDocument, CaseKnowledgeGraphRun, CaseSummaryRun
from app.services.case_analysis_processing import process_case_analysis
from app.services.document_processing import process_document_in_background
from app.services.knowledge_graph_processing import process_case_knowledge_graph
from app.services.summary_processing import process_case_summary


logger = logging.getLogger(__name__)
_WORKER_LOCK_ID = 731_204_119
_worker_state_lock = Lock()
_worker_state: dict[str, Any] = {
    "running": False,
    "current_task": None,
    "last_completed_at": None,
    "last_error": None,
}


def get_worker_status() -> dict[str, Any]:
    """Return process-local worker state without exposing exception details."""
    with _worker_state_lock:
        return dict(_worker_state)


def _set_worker_state(**updates: Any) -> None:
    with _worker_state_lock:
        _worker_state.update(updates)


def _recover_interrupted_work() -> None:
    with SessionLocal() as db:
        db.execute(
            update(CaseDocument)
            .where(CaseDocument.processing_status == "processing")
            .values(processing_status="queued")
        )
        db.execute(
            update(CaseAnalysisRun)
            .where(CaseAnalysisRun.status == "processing")
            .values(status="queued")
        )
        db.execute(
            update(CaseSummaryRun)
            .where(CaseSummaryRun.status == "processing")
            .values(status="queued")
        )
        db.execute(
            update(CaseKnowledgeGraphRun)
            .where(CaseKnowledgeGraphRun.status == "processing")
            .values(status="queued")
        )
        db.commit()


def _claim_next_task() -> tuple[str, Any, list[str] | None] | None:
    with SessionLocal() as db:
        # Pick the oldest task across all stages. Strictly prioritizing every
        # document over every analysis/summary/graph job can starve later stages
        # when uploads keep arriving.
        candidates = []
        for kind, model, timestamp_column, status_filter in (
            ("document", CaseDocument, CaseDocument.uploaded_at, CaseDocument.processing_status.in_({"uploaded", "queued"})),
            ("analysis", CaseAnalysisRun, CaseAnalysisRun.created_at, CaseAnalysisRun.status == "queued"),
            ("summary", CaseSummaryRun, CaseSummaryRun.created_at, CaseSummaryRun.status == "queued"),
            ("knowledge_graph", CaseKnowledgeGraphRun, CaseKnowledgeGraphRun.created_at, CaseKnowledgeGraphRun.status == "queued"),
        ):
            row = db.execute(
                select(model.id, timestamp_column)
                .where(status_filter)
                .order_by(timestamp_column, model.id)
                .limit(1)
            ).first()
            if row is not None:
                candidates.append((row[1], kind, model, row[0]))

        if not candidates:
            task = None
        else:
            _created_at, kind, model, task_id = min(candidates, key=lambda item: (item[0], item[1]))
            record = db.scalar(
                select(model).where(model.id == task_id).with_for_update(skip_locked=True)
            )
            if record is None:
                task = None
            elif kind == "document":
                record.processing_status = "processing"
                task = (kind, record.id, None)
            else:
                record.status = "processing"
                payload = list(record.advocate_claims or []) if kind == "analysis" else None
                task = (kind, record.id, payload)
        db.commit()
        return task


def _record_task_failure(task: tuple[str, Any, list[str] | None]) -> None:
    """Clear a claimed state if a processor failed before persisting its result."""
    kind, task_id, _payload = task
    with SessionLocal() as db:
        if kind == "document":
            record = db.get(CaseDocument, task_id)
            if record is not None and record.processing_status == "processing":
                record.processing_status = "failed"
                record.extraction_error = "Background processing stopped unexpectedly. Retry extraction."
        else:
            model = {
                "analysis": CaseAnalysisRun,
                "summary": CaseSummaryRun,
                "knowledge_graph": CaseKnowledgeGraphRun,
            }[kind]
            record = db.get(model, task_id)
            if record is not None and record.status == "processing":
                record.status = "failed"
                record.error_message = "Background processing stopped unexpectedly. Retry this operation."
                record.completed_at = datetime.now(UTC)
        db.commit()


async def _execute_task(task: tuple[str, Any, list[str] | None]) -> None:
    kind, task_id, payload = task
    if kind == "document":
        await asyncio.to_thread(process_document_in_background, task_id)
    elif kind == "analysis":
        await asyncio.to_thread(process_case_analysis, task_id, payload or [])
    elif kind == "knowledge_graph":
        await asyncio.to_thread(process_case_knowledge_graph, task_id)
    else:
        await asyncio.to_thread(process_case_summary, task_id)


def _try_sqlite_worker_lock():
    lock_key = hashlib.sha256(str(engine.url).encode("utf-8")).hexdigest()[:24]
    path = Path(tempfile.gettempdir()) / f"legal-engine-worker-{lock_key}.lock"
    handle = path.open("a+b")
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle
    except OSError:
        handle.close()
        return None


async def run_persistent_worker() -> None:
    """Recover unfinished work and keep polling despite transient failures."""
    lease_connection = None
    sqlite_lock = None
    try:
        if engine.dialect.name == "postgresql":
            lease_connection = engine.connect()
            while True:
                if lease_connection.execute(
                    text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": _WORKER_LOCK_ID}
                ).scalar():
                    break
                await asyncio.sleep(2)
        elif engine.dialect.name == "sqlite":
            while sqlite_lock is None:
                sqlite_lock = _try_sqlite_worker_lock()
                if sqlite_lock is None:
                    await asyncio.sleep(2)
    except BaseException:
        if lease_connection is not None:
            lease_connection.close()
        if sqlite_lock is not None:
            sqlite_lock.close()
        raise

    _set_worker_state(running=True, current_task=None, last_error=None)
    recovered = False
    try:
        while True:
            task: tuple[str, Any, list[str] | None] | None = None
            try:
                if not recovered:
                    _recover_interrupted_work()
                    recovered = True

                task = _claim_next_task()
                if task is None:
                    _set_worker_state(current_task=None)
                    await asyncio.sleep(1)
                    continue

                _set_worker_state(current_task={"kind": task[0]})
                task_id = str(task[1])
                started_at = perf_counter()
                logger.info("Starting persistent task kind=%s id=%s", task[0], task_id)
                await _execute_task(task)
                logger.info(
                    "Finished persistent task kind=%s id=%s elapsed_seconds=%.3f",
                    task[0], task_id, perf_counter() - started_at,
                )
                _set_worker_state(
                    current_task=None,
                    last_completed_at=datetime.now(UTC).isoformat(),
                    last_error=None,
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 — keep queue availability after a job/DB failure.
                logger.exception("Persistent worker iteration failed.")
                recovered = False
                _set_worker_state(
                    current_task=None,
                    last_error=type(error).__name__,
                )
                if task is not None:
                    try:
                        await asyncio.to_thread(_record_task_failure, task)
                    except Exception:  # noqa: BLE001 — the next process startup also recovers persisted processing states.
                        logger.exception("Could not persist the failed background task state.")
                await asyncio.sleep(2)
    finally:
        _set_worker_state(running=False, current_task=None)
        if lease_connection is not None:
            try:
                lease_connection.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": _WORKER_LOCK_ID})
            finally:
                lease_connection.close()
        if sqlite_lock is not None:
            if os.name != "nt":
                import fcntl
                fcntl.flock(sqlite_lock.fileno(), fcntl.LOCK_UN)
            sqlite_lock.close()
