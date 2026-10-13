import csv
import io
from datetime import timezone
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from .models import Application, Resume, StatusHistory
from .schemas import ApplicationIn

CSV_FIELDS = ['company', 'role', 'job_url', 'location', 'work_mode', 'salary', 'status',
              'application_date', 'deadline', 'recruiter_name', 'recruiter_email', 'notes']


def serialize(obj, exclude=()):
    result = {}
    for c in obj.__table__.columns:
        if c.name in exclude:
            continue
        value = getattr(obj, c.name)
        if hasattr(value, 'tzinfo') and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        result[c.name] = value
    return result


def owned(db, model, object_id, user_id):
    obj = db.scalar(select(model).where(model.id == object_id, model.user_id == user_id))
    if not obj:
        raise HTTPException(404, 'Record not found')
    return obj


def child_owned(db, model, object_id, user_id):
    obj = db.scalar(select(model).join(Application).where(model.id == object_id, Application.user_id == user_id))
    if not obj:
        raise HTTPException(404, 'Record not found')
    return obj


def save_application(db, user_id, data, app=None):
    if data.resume_id is not None:
        owned(db, Resume, data.resume_id, user_id)
    previous = app.status if app else None
    if app is None:
        app = Application(user_id=user_id)
        db.add(app)
    for key, value in data.model_dump().items():
        setattr(app, key, value)
    db.flush()
    if previous != app.status:
        db.add(StatusHistory(application_id=app.id, status=app.status))
    return app


def preview_csv(db, user_id, text):
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
    if not reader.fieldnames or set(reader.fieldnames) != set(CSV_FIELDS) or len(reader.fieldnames) != len(CSV_FIELDS):
        raise HTTPException(422, 'CSV headers must match the downloadable template')
    existing = {(a.company.casefold(), a.role.casefold(), a.application_date) for a in db.scalars(
        select(Application).where(Application.user_id == user_id))}
    rows, valid, errors = [], [], False
    try:
        for number, raw in enumerate(reader, start=2):
            if number > 501:
                raise HTTPException(422, 'Import at most 500 rows at a time')
            try:
                if None in raw or any(v is None for v in raw.values()):
                    raise ValueError('Wrong number of columns')
                for k in ('application_date', 'deadline'):
                    raw[k] = raw[k] or None
                data = ApplicationIn(**raw)
                key = (data.company.casefold(), data.role.casefold(), data.application_date)
                duplicate = key in existing
                existing.add(key)
                rows.append({'row': number, 'company': data.company, 'role': data.role,
                             'result': 'duplicate — skipped' if duplicate else 'ready'})
                if not duplicate:
                    valid.append(data)
            except (ValidationError, ValueError) as exc:
                errors = True
                msg = '; '.join(f"{'.'.join(map(str, e['loc'])) or 'row'}: {e['msg']}" for e in exc.errors()) if isinstance(exc, ValidationError) else str(exc)
                rows.append({'row': number, 'result': 'error', 'error': msg})
    except csv.Error:
        raise HTTPException(422, 'Malformed CSV')
    return {'rows': rows, 'ready': len(valid), 'has_errors': errors}, valid


def csv_output(apps):
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for app in apps:
        row = {}
        for key in CSV_FIELDS:
            value = str(getattr(app, key) or '')
            # Spreadsheet formula protection, including leading whitespace/control bytes.
            if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
                value = "'" + value
            row[key] = value
        writer.writerow(row)
    return out.getvalue()
