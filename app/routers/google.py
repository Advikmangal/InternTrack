"""Google sign-in, explicit Gmail consent, and a reviewable email import queue."""
import html
import secrets
from datetime import timedelta, datetime, timezone, date
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, delete, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession
from .. import google
from ..auth import current_user, digest, make_session, hasher
from ..config import settings
from ..database import get_db
from ..models import User, Session, GoogleAccount, GoogleOAuthState, EmailCandidate, Application, StatusHistory, now
from ..schemas import ApplicationIn, Status
from ..services import serialize, owned, save_application
from .authentication import rotate

router = APIRouter(prefix='/api/google', tags=['Google and Gmail'])
COOKIE = 'interntrack_google_state'


def begin(request, db, purpose, session_hash=None):
    if not google.configured():
        raise HTTPException(503, 'Google sign-in is not configured. Set the Google OAuth environment variables.')
    if purpose == 'connect':
        google.cipher()
    state, browser, verifier = (secrets.token_urlsafe(48) for _ in range(3))
    db.execute(delete(GoogleOAuthState).where(GoogleOAuthState.expires_at < now()).execution_options(synchronize_session=False))
    db.add(GoogleOAuthState(state_hash=digest(state), browser_hash=digest(browser), verifier=verifier,
                           purpose=purpose, session_hash=session_hash, expires_at=now() + timedelta(minutes=10)))
    db.commit()
    params = {'client_id': settings.google_client_id, 'redirect_uri': settings.google_redirect_uri,
              'response_type': 'code', 'scope': 'openid email profile' + (' ' + google.GMAIL_SCOPE if purpose == 'connect' else ''),
              'state': state, 'code_challenge': google.challenge(verifier), 'code_challenge_method': 'S256',
              'prompt': 'consent' if purpose == 'connect' else 'select_account'}
    if purpose == 'connect':
        params['access_type'] = 'offline'
    response = RedirectResponse('https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(params), status_code=303)
    response.set_cookie(COOKIE, browser, max_age=600, httponly=True, secure=settings.cookie_secure, samesite='lax', path='/api/google')
    return response


@router.get('/login')
def login(request: Request, db: DBSession = Depends(get_db)):
    if not google.configured():
        return RedirectResponse('/?google=not_configured', status_code=303)
    return begin(request, db, 'login')


@router.post('/connect')
def connect(request: Request, user=Depends(current_user), db: DBSession = Depends(get_db)):
    response = begin(request, db, 'connect', request.state.session.token_hash)
    # Fetch must not follow an external redirect; the frontend navigates explicitly.
    from fastapi.responses import JSONResponse
    result = JSONResponse({'url': response.headers['location']})
    result.headers['set-cookie'] = response.headers['set-cookie']
    return result


@router.get('/callback')
def callback(request: Request, state: str = '', code: str = '', error: str = '', db: DBSession = Depends(get_db)):
    response = RedirectResponse('/?google=failed#emails', status_code=303)
    response.delete_cookie(COOKIE, path='/api/google', secure=settings.cookie_secure, httponly=True, samesite='lax')
    flow = db.scalar(select(GoogleOAuthState).where(GoogleOAuthState.state_hash == digest(state)).with_for_update()) if state else None
    if not flow or google.utc(flow.expires_at) <= now() or not secrets.compare_digest(flow.browser_hash, digest(request.cookies.get(COOKIE, ''))):
        response.headers['location'] = '/?google=invalid_state'
        return response
    purpose, session_hash, verifier = flow.purpose, flow.session_hash, flow.verifier
    db.delete(flow)
    db.commit()  # Consume once, including denied or failed attempts.
    if error or not code:
        response.headers['location'] = '/?google=cancelled#emails'
        return response
    try:
        user = None
        if purpose == 'connect':
            session = db.get(Session, session_hash)
            if not session or google.utc(session.expires_at) <= now() or digest(request.cookies.get(settings.cookie_name, '')) != session_hash:
                raise HTTPException(401, 'Session changed')
            user = db.get(User, session.user_id)
        tokens = google.google_request('POST', google.TOKEN_URL, data={
            'code': code, 'client_id': settings.google_client_id, 'client_secret': settings.google_client_secret,
            'redirect_uri': settings.google_redirect_uri, 'grant_type': 'authorization_code', 'code_verifier': verifier,
        })
        identity = google.google_request('GET', 'https://openidconnect.googleapis.com/v1/userinfo',
                                         headers={'Authorization': 'Bearer ' + tokens['access_token']})
        email = str(identity.get('email', '')).lower()
        if identity.get('email_verified') is not True or not identity.get('sub') or not email or len(email) > 254:
            raise HTTPException(400, 'Google email is not verified')
        account = db.scalar(select(GoogleAccount).where(GoogleAccount.subject == identity['sub']))
        if purpose == 'login':
            if account:
                user = db.get(User, account.user_id)
            else:
                if db.scalar(select(User).where(User.email == email)):
                    response.headers['location'] = '/?google=link_required'
                    return response
                user = User(name=(identity.get('name') or email.split('@')[0])[:100], email=email,
                            password_hash=hasher.hash(secrets.token_urlsafe(48)))
                db.add(user)
                db.flush()
                account = GoogleAccount(user_id=user.id, subject=identity['sub'], email=email)
                db.add(account)
            rotate(db, request)
            make_session(db, user, response)
            response.headers['location'] = '/?google=signed_in#emails'
        else:
            existing = db.get(GoogleAccount, user.id)
            if email != user.email or (account and account.user_id != user.id) or (existing and existing.subject != identity['sub']):
                response.headers['location'] = '/?google=wrong_account#emails'
                return response
            if google.GMAIL_SCOPE not in tokens.get('scope', '').split():
                response.headers['location'] = '/?google=missing_permission#emails'
                return response
            if not account:
                account = GoogleAccount(user_id=user.id, subject=identity['sub'], email=email)
                db.add(account)
            refresh = tokens.get('refresh_token')
            if not refresh and not account.refresh_token:
                raise HTTPException(409, 'No refresh token')
            if refresh:
                account.refresh_token = google.cipher().encrypt(refresh.encode()).decode()
            response.headers['location'] = '/?google=connected#emails'
        db.commit()
    except (HTTPException, IntegrityError, KeyError, ValueError):
        db.rollback()
        # Never put provider errors, codes or tokens in the redirect.
        response.headers['location'] = '/?google=failed#emails'
        if purpose == 'login':
            response.delete_cookie(settings.cookie_name, path='/', secure=settings.cookie_secure, httponly=True, samesite='lax')
    return response


@router.get('/status')
def status(user=Depends(current_user), db: DBSession = Depends(get_db)):
    account = db.get(GoogleAccount, user.id)
    return {'configured': google.configured(), 'gmail_configured': google.configured() and bool(settings.google_token_key),
            'linked': bool(account), 'connected': bool(account and account.refresh_token),
            'email': account.email if account else None,
            'last_synced_at': google.utc(account.last_synced_at) if account and account.last_synced_at else None,
            'has_more': bool(account and account.page_token)}


@router.post('/disconnect', status_code=204)
def disconnect(user=Depends(current_user), db: DBSession = Depends(get_db)):
    account = db.scalar(select(GoogleAccount).where(GoogleAccount.user_id == user.id).with_for_update())
    if account:
        # Forget local access without revoking the Google identity used to log in.
        account.refresh_token = None
        account.page_token = None
        account.last_synced_at = None
        account.sync_started_at = None
    db.execute(delete(EmailCandidate).where(EmailCandidate.user_id == user.id))
    db.commit()


@router.post('/sync')
def sync(user=Depends(current_user), db: DBSession = Depends(get_db)):
    account = db.scalar(select(GoogleAccount).where(GoogleAccount.user_id == user.id).with_for_update())
    if not account or not account.refresh_token:
        raise HTTPException(409, 'Connect Gmail first')
    if not account.page_token and account.last_synced_at and now() - google.utc(account.last_synced_at) < timedelta(seconds=60):
        return {'added': 0, 'has_more': False}
    headers = {'Authorization': 'Bearer ' + google.access_token(account)}
    if not account.page_token:
        account.sync_started_at = now()
    since = google.utc(account.last_synced_at) - timedelta(days=2) if account.last_synced_at else google.utc(account.sync_started_at) - timedelta(days=90)
    params = {'q': google.QUERY + ' after:' + str(int(since.timestamp())), 'maxResults': 50}
    if account.page_token:
        params['pageToken'] = account.page_token
    try:
        batch = google.google_request('GET', google.GMAIL_URL + '/messages', headers=headers, params=params)
    except HTTPException as exc:
        if exc.status_code == 409 and account.page_token:
            account.page_token = None  # Restart expired pagination with message-id deduplication.
            db.commit()
        raise
    added = 0
    for item in batch.get('messages', []):
        message_id = item['id']
        if db.scalar(select(EmailCandidate.id).where(EmailCandidate.user_id == user.id, EmailCandidate.message_id == message_id)):
            continue
        try:
            message = google.google_request('GET', google.GMAIL_URL + '/messages/' + message_id,
                                            headers=headers, params={'format': 'metadata', 'metadataHeaders': ['Subject', 'From']})
        except HTTPException as exc:
            if exc.status_code == 404:
                continue  # Mail can be deleted between listing and fetching it.
            raise  # Roll back the whole batch; never advance past an unread message.
        fields = {h['name'].lower(): h['value'] for h in message.get('payload', {}).get('headers', [])}
        subject, snippet = fields.get('subject', ''), html.unescape(message.get('snippet', ''))
        suggestion = google.classify(subject, snippet)
        if suggestion:
            db.add(EmailCandidate(user_id=user.id, message_id=message_id, subject=subject[:500],
                                  sender=fields.get('from', '')[:500], snippet=snippet[:2000],
                                  received_at=datetime.fromtimestamp(int(message['internalDate']) / 1000, timezone.utc), **suggestion))
            added += 1
    account.page_token = batch.get('nextPageToken')
    if not account.page_token:
        account.last_synced_at = account.sync_started_at
        account.sync_started_at = None
    db.commit()
    return {'added': added, 'has_more': bool(account.page_token)}


@router.get('/emails')
def emails(page: int = Query(1, ge=1), user=Depends(current_user), db: DBSession = Depends(get_db)):
    stmt = select(EmailCandidate).where(EmailCandidate.user_id == user.id, EmailCandidate.reviewed.is_(False))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(stmt.order_by(EmailCandidate.received_at.desc(), EmailCandidate.id.desc()).offset((page-1)*25).limit(25))
    return {'items': [serialize(item, exclude=('user_id',)) for item in items], 'total': total, 'page': page}


class Review(BaseModel):
    application_id: int | None = Field(default=None, gt=0)
    company: str = Field(default='', max_length=160)
    role: str = Field(default='', max_length=160)
    status: Status = 'Applied'
    application_date: date | None = None


@router.post('/emails/{email_id}/import')
def import_email(email_id: int, data: Review, user=Depends(current_user), db: DBSession = Depends(get_db)):
    item = db.scalar(select(EmailCandidate).where(EmailCandidate.id == email_id, EmailCandidate.user_id == user.id).with_for_update())
    if not item:
        raise HTTPException(404, 'Email not found')
    if item.reviewed:
        raise HTTPException(409, 'Email already reviewed')
    if data.application_id:
        application = owned(db, Application, data.application_id, user.id)
        if application.status != data.status:
            application.status = data.status
            application.application_date = application.application_date or data.application_date or item.received_at.date()
            db.add(StatusHistory(application_id=application.id, status=data.status))
    else:
        if not data.company.strip() or not data.role.strip():
            raise HTTPException(422, 'Enter the company and role before importing')
        applied = data.application_date or item.received_at.date()
        duplicate = db.scalar(select(Application).where(Application.user_id == user.id,
                              func.lower(Application.company) == data.company.strip().lower(),
                              func.lower(Application.role) == data.role.strip().lower(), Application.application_date == applied))
        if duplicate:
            raise HTTPException(409, 'This application already exists. Select it to update its status.')
        application = save_application(db, user.id, ApplicationIn(company=data.company, role=data.role,
                        status=data.status, application_date=applied, notes='Imported from email: ' + item.subject))
    item.reviewed = True
    item.application_id = application.id
    db.commit()
    return {'application_id': application.id}


@router.post('/emails/{email_id}/dismiss', status_code=204)
def dismiss(email_id: int, user=Depends(current_user), db: DBSession = Depends(get_db)):
    item = owned(db, EmailCandidate, email_id, user.id)
    item.reviewed = True
    db.commit()
