from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession
from ..auth import current_user, hasher, make_session, verify_password, dummy_hash, digest
from ..config import settings
from ..database import get_db
from ..models import User, Session
from ..schemas import Register, Login, Preferences

router = APIRouter(prefix='/api/auth', tags=['Authentication'])


def profile(user, csrf):
    return {'id': user.id, 'name': user.name, 'email': user.email, 'timezone': user.timezone, 'csrf': csrf}


def rotate(db, request):
    old = db.get(Session, digest(request.cookies.get(settings.cookie_name, '')))
    if old:
        db.delete(old)


@router.post('/register', status_code=201)
def register(data: Register, request: Request, response: Response, db: DBSession = Depends(get_db)):
    user = User(name=data.name, email=str(data.email).lower(), password_hash=hasher.hash(data.password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'An account with this email already exists')
    rotate(db, request)
    csrf = make_session(db, user, response)
    db.commit()
    return profile(user, csrf)


@router.post('/login')
def login(data: Login, request: Request, response: Response, db: DBSession = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    correct = verify_password(user.password_hash if user else dummy_hash, data.password)
    if not user or not correct:
        raise HTTPException(401, 'Incorrect email or password')
    rotate(db, request)
    csrf = make_session(db, user, response)
    db.commit()
    return profile(user, csrf)


@router.get('/me')
def me(request: Request, user=Depends(current_user)):
    return profile(user, request.state.session.csrf)


@router.patch('/me')
def preferences(data: Preferences, request: Request, user=Depends(current_user), db: DBSession = Depends(get_db)):
    user.name, user.timezone = data.name, data.timezone
    db.commit()
    return profile(user, request.state.session.csrf)


@router.post('/logout', status_code=204)
def logout(request: Request, response: Response, user=Depends(current_user), db: DBSession = Depends(get_db)):
    db.delete(request.state.session)
    db.commit()
    response.delete_cookie(settings.cookie_name, path='/', secure=settings.cookie_secure, httponly=True, samesite='lax')
