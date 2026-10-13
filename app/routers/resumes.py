from uuid import uuid4
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..auth import current_user
from ..config import settings
from ..database import get_db
from ..models import Resume
from ..services import owned, serialize
from ..files import validate_pdf

router = APIRouter(prefix='/api/resumes', tags=['Résumés'])


@router.get('')
def listing(user=Depends(current_user), db: Session = Depends(get_db)):
    return [serialize(r, ('filename',)) for r in db.scalars(select(Resume).where(Resume.user_id == user.id).order_by(Resume.created_at.desc()))]


@router.post('', status_code=201)
async def upload(name: str = Form(min_length=1, max_length=100), file: UploadFile = File(),
                 user=Depends(current_user), db: Session = Depends(get_db)):
    content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    await file.close()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f'PDF must be at most {settings.max_upload_mb} MB')
    validate_pdf(file.filename, content)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    filename = uuid4().hex + '.pdf'
    path = settings.upload_dir / filename
    path.write_bytes(content)
    item = Resume(user_id=user.id, name=name.strip(), filename=filename, size=len(content))
    try:
        db.add(item)
        db.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return serialize(item, ('filename',))


@router.get('/{item_id}/download')
def download(item_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
    item = owned(db, Resume, item_id, user.id)
    path = settings.upload_dir / item.filename
    if not path.is_file():
        raise HTTPException(404, 'File is unavailable')
    return FileResponse(path, media_type='application/pdf', filename=f'resume-{item.id}.pdf',
                        headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


@router.delete('/{item_id}', status_code=204)
def delete(item_id: int, user=Depends(current_user), db: Session = Depends(get_db)):
    item = owned(db, Resume, item_id, user.id)
    path = settings.upload_dir / item.filename
    db.delete(item)
    db.commit()  # FK SET NULL preserves applications.
    path.unlink(missing_ok=True)
