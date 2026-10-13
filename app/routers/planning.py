from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..auth import current_user
from ..database import get_db
from ..models import Application, Interview, FollowUp, now
from ..schemas import InterviewIn, FollowUpIn, CompleteFollowUp
from ..services import owned, child_owned, serialize

router = APIRouter(prefix='/api', tags=['Interviews and follow-ups'])


@router.get('/interviews')
def interviews(upcoming: bool = False, user=Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Interview, Application.company, Application.role).join(Application).where(Application.user_id == user.id)
    if upcoming:
        stmt = stmt.where(Interview.starts_at >= now())
    return [{**serialize(i), 'company': c, 'role': r} for i, c, r in db.execute(stmt.order_by(Interview.starts_at))]


@router.post('/applications/{app_id}/interviews', status_code=201)
def add_interview(app_id: int, data: InterviewIn, user=Depends(current_user), db: Session = Depends(get_db)):
    owned(db, Application, app_id, user.id)
    item = Interview(application_id=app_id, **data.model_dump())
    db.add(item)
    db.commit()
    return serialize(item)


@router.put('/interviews/{item_id}')
def edit_interview(item_id: int, data: InterviewIn, user=Depends(current_user), db: Session = Depends(get_db)):
    item = child_owned(db, Interview, item_id, user.id)
    for k, v in data.model_dump().items():
        setattr(item, k, v)
    db.commit()
    return serialize(item)


@router.delete('/interviews/{item_id}', status_code=204)
def delete_interview(item_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
    db.delete(child_owned(db, Interview, item_id, user.id))
    db.commit()


@router.get('/follow-ups')
def followups(user=Depends(current_user), db: Session = Depends(get_db)):
    today = datetime.now(ZoneInfo(user.timezone)).date()
    stmt = select(FollowUp, Application.company, Application.role).join(Application).where(Application.user_id == user.id).order_by(FollowUp.due_date)
    return [{**serialize(f), 'company': c, 'role': r,
             'bucket': 'completed' if f.completed_at else 'overdue' if f.due_date < today else 'today' if f.due_date == today else 'upcoming'}
            for f, c, r in db.execute(stmt)]


@router.post('/applications/{app_id}/follow-ups', status_code=201)
def add_followup(app_id: int, data: FollowUpIn, user=Depends(current_user), db: Session = Depends(get_db)):
    owned(db, Application, app_id, user.id)
    item = FollowUp(application_id=app_id, due_date=data.due_date)
    db.add(item)
    db.commit()
    return serialize(item)


@router.put('/follow-ups/{item_id}')
def edit_followup(item_id: int, data: FollowUpIn, user=Depends(current_user), db: Session = Depends(get_db)):
    item = child_owned(db, FollowUp, item_id, user.id)
    if item.completed_at:
        raise HTTPException(409, 'Completed follow-ups cannot be rescheduled')
    item.due_date = data.due_date
    db.commit()
    return serialize(item)


@router.post('/follow-ups/{item_id}/complete')
def complete(item_id: int, data: CompleteFollowUp, user=Depends(current_user), db: Session = Depends(get_db)):
    item = child_owned(db, FollowUp, item_id, user.id)
    if item.completed_at:
        raise HTTPException(409, 'Follow-up already completed')
    item.completed_at = now()
    if data.next_date:
        db.add(FollowUp(application_id=item.application_id, due_date=data.next_date))
    db.commit()
    return serialize(item)


@router.delete('/follow-ups/{item_id}', status_code=204)
def delete_followup(item_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
    db.delete(child_owned(db, FollowUp, item_id, user.id))
    db.commit()
