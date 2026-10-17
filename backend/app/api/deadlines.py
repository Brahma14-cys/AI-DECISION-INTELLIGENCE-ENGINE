from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.db.models import Case, CaseDeadline
from app.schemas.cases import CaseDeadlineCreate, CaseDeadlineRead, CaseDeadlineUpdate


router = APIRouter(prefix="/cases", tags=["case-deadlines"])


def _require_case(db: Session, case_id: UUID) -> None:
    if db.get(Case, case_id) is None:
        raise HTTPException(status_code=404, detail="Case not found.")


@router.get("/{case_id}/deadlines", response_model=list[CaseDeadlineRead])
def list_case_deadlines(case_id: UUID, db: Session = Depends(get_db)) -> list[CaseDeadline]:
    _require_case(db, case_id)
    return list(db.scalars(
        select(CaseDeadline).where(CaseDeadline.case_id == case_id)
        .order_by(CaseDeadline.due_date, CaseDeadline.created_at)
    ).all())


@router.post("/{case_id}/deadlines", response_model=CaseDeadlineRead, status_code=status.HTTP_201_CREATED)
def create_case_deadline(
    case_id: UUID, payload: CaseDeadlineCreate, db: Session = Depends(get_db)
) -> CaseDeadline:
    _require_case(db, case_id)
    deadline = CaseDeadline(case_id=case_id, **payload.model_dump())
    db.add(deadline)
    case = db.get(Case, case_id)
    if case is not None:
        case.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(deadline)
    return deadline


@router.patch("/{case_id}/deadlines/{deadline_id}", response_model=CaseDeadlineRead)
def update_case_deadline(
    case_id: UUID, deadline_id: UUID, payload: CaseDeadlineUpdate, db: Session = Depends(get_db)
) -> CaseDeadline:
    deadline = db.scalar(select(CaseDeadline).where(
        CaseDeadline.id == deadline_id, CaseDeadline.case_id == case_id
    ))
    if deadline is None:
        raise HTTPException(status_code=404, detail="Deadline not found in this case.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(deadline, field, value)
    case = db.get(Case, case_id)
    if case is not None:
        case.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(deadline)
    return deadline


@router.delete("/{case_id}/deadlines/{deadline_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case_deadline(case_id: UUID, deadline_id: UUID, db: Session = Depends(get_db)) -> Response:
    deadline = db.scalar(select(CaseDeadline).where(
        CaseDeadline.id == deadline_id, CaseDeadline.case_id == case_id
    ))
    if deadline is None:
        raise HTTPException(status_code=404, detail="Deadline not found in this case.")
    case = db.get(Case, case_id)
    if case is not None:
        case.updated_at = datetime.now(UTC)
    db.delete(deadline)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
