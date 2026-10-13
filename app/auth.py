import hashlib
import secrets
from datetime import timedelta, timezone
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session as DBSession
from .database import get_db
from .models import Session, User, now
from .config import settings

hasher = PasswordHasher()
# Equal-cost password verification when an account does not exist.
dummy_hash = hasher.hash(secrets.token_urlsafe(32))


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def verify_password(stored, password):
    try:
        return hasher.verify(stored, password)
    except VerificationError:
        return False


def make_session(db, user, response):
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    db.add(Session(token_hash=digest(token), user_id=user.id, csrf=csrf,
                   expires_at=now() + timedelta(days=settings.session_days)))
    response.set_cookie(settings.cookie_name, token, httponly=True,
                        secure=settings.cookie_secure, samesite='lax', path='/',
                        max_age=settings.session_days * 86400)
    return csrf


def current_user(request: Request, db: DBSession = Depends(get_db)):
    token = request.cookies.get(settings.cookie_name, '')
    session = db.get(Session, digest(token)) if token else None
    expires = session.expires_at if session else None
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if not session or expires <= now():
        raise HTTPException(401, 'Please log in to continue')
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), session.csrf):
            raise HTTPException(403, 'Invalid CSRF token. Refresh the page and try again.')
    request.state.session = session
    return db.get(User, session.user_id)
