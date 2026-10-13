from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, Query, Response, HTTPException
from sqlalchemy import select, or_, func
from sqlalchemy.orm import Session
from ..auth import current_user
from ..database import get_db
from ..models import Application, StatusHistory, Interview, FollowUp, Resume
from ..schemas import ApplicationIn, StatusIn, Status, Mode, CSVIn, ResumeAttachmentIn
from ..services import owned, save_application, serialize, preview_csv, csv_output

router = APIRouter(prefix='/api/applications', tags=['Applications'])


@router.get('/export')
def export(user=Depends(current_user), db: Session = Depends(get_db)):
    apps = db.scalars(select(Application).where(Application.user_id == user.id).order_by(Application.id))
    return Response(csv_output(apps), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="interntrack.csv"'})


@router.get('/template')
def template(user=Depends(current_user)):
    return Response(csv_output([]), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="import-template.csv"'})


@router.post('/import/preview')
def preview(data: CSVIn, user=Depends(current_user), db: Session = Depends(get_db)):
    result, _ = preview_csv(db, user.id, data.text)
    return result


@router.post('/import', status_code=201)
def import_csv(data: CSVIn, user=Depends(current_user), db: Session = Depends(get_db)):
    # Always revalidate at save time; preview is not trusted input.
    result, rows = preview_csv(db, user.id, data.text)
    if result['has_errors']:
        raise HTTPException(422, 'Fix all row errors before importing')
    for row in rows:
        save_application(db, user.id, row)
    db.commit()
    return {'imported': len(rows), 'skipped': len(result['rows']) - len(rows)}


@router.get('')
def listing(q: str = Query('', max_length=160), status: Status | None = None, work_mode: Mode | None = None,
            date_from: date | None = None, date_to: date | None = None,
            group: Literal['submitted', 'active'] | None = None,
            sort: Literal['newest', 'oldest', 'deadline', 'company'] = 'newest',
            page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=100),
            user=Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Application).where(Application.user_id == user.id)
    if q:
        pattern = '%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        stmt = stmt.where(or_(Application.company.ilike(pattern, escape='\\'), Application.role.ilike(pattern, escape='\\')))
    if status:
        stmt = stmt.where(Application.status == status)
    if work_mode:
        stmt = stmt.where(Application.work_mode == work_mode)
    if date_from:
        stmt = stmt.where(Application.application_date >= date_from)
    if date_to:
        stmt = stmt.where(Application.application_date <= date_to)
    if group == 'submitted':
        stmt = stmt.where(Application.status != 'Saved')
    if group == 'active':
        stmt = stmt.where(Application.status.in_(['Applied', 'Assessment', 'Interview']))
    count = db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = {'newest': Application.created_at.desc(), 'oldest': Application.created_at,
             'deadline': Application.deadline.asc().nulls_last(), 'company': func.lower(Application.company)}[sort]
    apps = db.scalars(stmt.order_by(order, Application.id).offset((page - 1) * page_size).limit(page_size))
    return {'items': [serialize(a) for a in apps], 'total': count, 'page': page, 'page_size': page_size}


@router.post('', status_code=201)
def create(data: ApplicationIn, user=Depends(current_user), db: Session = Depends(get_db)):
    app = save_application(db, user.id, data)
    db.commit()
    return serialize(app)


@router.get('/{app_id}')
def detail(app_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
    app = owned(db, Application, app_id, user.id)
    result = serialize(app)
    result['history'] = [serialize(h) for h in db.scalars(select(StatusHistory).where(StatusHistory.application_id == app_id).order_by(StatusHistory.changed_at, StatusHistory.id))]
    result['interviews'] = [serialize(i) for i in db.scalars(select(Interview).where(Interview.application_id == app_id).order_by(Interview.starts_at))]
    result['follow_ups'] = [serialize(f) for f in db.scalars(select(FollowUp).where(FollowUp.application_id == app_id).order_by(FollowUp.due_date))]
    return result


@router.put('/{app_id}')
def update(app_id: int, data: ApplicationIn, user=Depends(current_user), db: Session = Depends(get_db)):
    app = save_application(db, user.id, data, owned(db, Application, app_id, user.id))
    db.commit()
    return serialize(app)


@router.patch('/{app_id}/resume')
def attach_resume(app_id: int, data: ResumeAttachmentIn, user=Depends(current_user), db: Session = Depends(get_db)):
    app = owned(db, Application, app_id, user.id)
    if data.resume_id is not None:
        owned(db, Resume, data.resume_id, user.id)
    app.resume_id = data.resume_id
    db.commit()
    return serialize(app)


@router.patch('/{app_id}/status')
def status(app_id: int, data: StatusIn, user=Depends(current_user), db: Session = Depends(get_db)):
    app = owned(db, Application, app_id, user.id)
    values = {k: getattr(app, k) for k in ApplicationIn.model_fields}
    values['status'] = data.status
    if data.application_date:
        values['application_date'] = data.application_date
    if data.status != 'Saved' and not values['application_date']:
        raise HTTPException(422, 'Provide an application date when moving a saved job')
    save_application(db, user.id, ApplicationIn(**values), app)
    db.commit()
    return serialize(app)


@router.delete('/{app_id}', status_code=204)
def delete(app_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
    db.delete(owned(db, Application, app_id, user.id))
    db.commit()
