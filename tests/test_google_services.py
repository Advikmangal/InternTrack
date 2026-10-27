"""Database-level coverage that does not require a network-capable event loop."""
from datetime import timedelta
from http.cookies import SimpleCookie
from urllib.parse import urlparse, parse_qs
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from starlette.requests import Request
from app.database import Base
from app import google
from app.auth import digest
from app.config import settings
from app.models import User, GoogleAccount, Session as LoginSession, GoogleOAuthState, EmailCandidate, Application, StatusHistory, now
from app.routers import google as routes
from tests.test_google import provider


@pytest.fixture
def db():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def request(cookies=''):
    return Request({'type': 'http', 'method': 'GET', 'path': '/api/google/callback', 'headers': [(b'cookie', cookies.encode())]})


def flow(db, purpose='login', session_hash=None):
    result = routes.begin(request(), db, purpose, session_hash)
    cookie = SimpleCookie(result.headers['set-cookie'])
    state = parse_qs(urlparse(result.headers['location']).query)['state'][0]
    return state, f"{routes.COOKIE}={cookie[routes.COOKIE].value}"


def test_services_oauth_signup_binding_replay(db, provider):
    state, cookie = flow(db)
    assert 'invalid_state' in routes.callback(request(), state, 'code', '', db).headers['location']
    result = routes.callback(request(cookie), state, 'code', '', db)
    assert 'signed_in' in result.headers['location']
    user = db.scalar(select(User))
    assert user.email == 'alice@example.com'
    assert db.get(GoogleAccount, user.id).refresh_token is None
    assert db.scalar(select(LoginSession)).user_id == user.id
    assert 'invalid_state' in routes.callback(request(cookie), state, 'code', '', db).headers['location']
    state, cookie = flow(db)
    assert 'signed_in' in routes.callback(request(cookie), state, 'code', '', db).headers['location']
    assert len(list(db.scalars(select(User)))) == 1


def test_services_account_linking_and_scope(db, provider):
    user = User(name='Alice', email='alice@example.com', password_hash='unused')
    db.add(user); db.flush()
    token = 'session-secret'
    db.add(LoginSession(token_hash=digest(token), user_id=user.id, csrf='csrf', expires_at=now()+timedelta(days=1)))
    db.commit()
    state, cookie = flow(db)
    assert 'link_required' in routes.callback(request(cookie), state, 'code', '', db).headers['location']
    for change, expected in [({'email': 'other@example.com'}, 'wrong_account'), ({'email': user.email, 'scope': 'openid'}, 'missing_permission'), ({'scope': google.GMAIL_SCOPE}, 'connected')]:
        provider.update(change)
        state, cookie = flow(db, 'connect', digest(token))
        result = routes.callback(request(cookie + f'; {settings.cookie_name}={token}'), state, 'code', '', db)
        assert expected in result.headers['location']
    assert db.get(GoogleAccount, user.id).refresh_token.startswith('test-encrypted:')
    assert routes.status(user, db)['connected']
    state, cookie = flow(db, 'connect', digest(token))
    assert 'failed' in routes.callback(request(cookie), state, 'code', '', db).headers['location']


def test_services_expired_cancelled_unverified(db, provider):
    state, cookie = flow(db)
    stored = db.get(GoogleOAuthState, digest(state)); stored.expires_at = now()-timedelta(seconds=1); db.commit()
    assert 'invalid_state' in routes.callback(request(cookie), state, 'code', '', db).headers['location']
    state, cookie = flow(db)
    assert 'cancelled' in routes.callback(request(cookie), state, '', 'access_denied', db).headers['location']
    assert db.get(GoogleOAuthState, digest(state)) is None
    provider['verified'] = False
    state, cookie = flow(db)
    assert 'failed' in routes.callback(request(cookie), state, 'code', '', db).headers['location']
    assert db.scalar(select(User)) is None


def test_services_sync_import_isolation_and_disconnect(db, provider, monkeypatch):
    user = User(name='Alice', email='alice@example.com', password_hash='unused')
    other = User(name='Bob', email='bob@example.com', password_hash='unused')
    db.add_all([user, other]); db.flush()
    account = GoogleAccount(user_id=user.id, subject='google-alice', email=user.email, refresh_token='encrypted')
    db.add(account); db.commit()
    monkeypatch.setattr(google, 'access_token', lambda account: 'access')
    def gmail(method, url, **kwargs):
        if url.endswith('/messages'):
            return {'messages': [{'id': 'one'}, {'id': 'two'}], **({} if kwargs['params'].get('pageToken') else {'nextPageToken': 'page2'})}
        return {'payload': {'headers': [{'name': 'Subject', 'value': 'You applied for Backend Intern at Acme'}]}, 'snippet': 'Application received', 'internalDate': '1793000000000'}
    monkeypatch.setattr(google, 'google_request', gmail)
    assert routes.sync(user, db) == {'added': 2, 'has_more': True}
    assert routes.sync(user, db) == {'added': 0, 'has_more': False}
    assert routes.emails(1, other, db)['total'] == 0
    queue = routes.emails(1, user, db)['items']
    with pytest.raises(HTTPException) as err:
        routes.import_email(queue[0]['id'], routes.Review(company='Acme', role='Backend Intern'), other, db)
    assert err.value.status_code == 404
    result = routes.import_email(queue[0]['id'], routes.Review(company='Acme', role='Backend Intern'), user, db)
    app_id = result['application_id']
    with pytest.raises(HTTPException) as err:
        routes.import_email(queue[0]['id'], routes.Review(company='Acme', role='Backend Intern'), user, db)
    assert err.value.status_code == 409
    with pytest.raises(HTTPException) as err:
        routes.import_email(queue[1]['id'], routes.Review(company='Acme', role='Backend Intern'), user, db)
    assert err.value.status_code == 409
    routes.import_email(queue[1]['id'], routes.Review(application_id=app_id, status='Interview'), user, db)
    assert db.get(Application, app_id).status == 'Interview'
    assert [h.status for h in db.scalars(select(StatusHistory).order_by(StatusHistory.id))] == ['Applied', 'Interview']
    routes.disconnect(user, db)
    assert not routes.status(user, db)['connected']
    assert routes.status(user, db)['linked']
    assert db.get(Application, app_id)
    assert routes.emails(1, user, db)['total'] == 0


def test_services_failed_sync_preserves_checkpoint(db, provider, monkeypatch):
    user = User(name='Alice', email='alice@example.com', password_hash='unused')
    db.add(user); db.flush()
    db.add(GoogleAccount(user_id=user.id, subject='alice', email=user.email, refresh_token='token')); db.commit()
    monkeypatch.setattr(google, 'access_token', lambda account: 'access')
    def fail(method, url, **kwargs):
        if url.endswith('/messages'):
            return {'messages': [{'id': 'one'}], 'nextPageToken': 'page2'}
        raise HTTPException(502, 'Unavailable')
    monkeypatch.setattr(google, 'google_request', fail)
    with pytest.raises(HTTPException):
        routes.sync(user, db)
    db.rollback()
    assert routes.status(user, db)['last_synced_at'] is None
    assert not routes.status(user, db)['has_more']


def test_services_deleted_mail_does_not_block_sync(db, provider, monkeypatch):
    user = User(name='Alice', email='alice@example.com', password_hash='unused')
    db.add(user); db.flush()
    db.add(GoogleAccount(user_id=user.id, subject='alice', email=user.email, refresh_token='token')); db.commit()
    monkeypatch.setattr(google, 'access_token', lambda account: 'access')
    def deleted(method, url, **kwargs):
        if url.endswith('/messages'):
            return {'messages': [{'id': 'deleted'}]}
        raise HTTPException(404, 'Gone')
    monkeypatch.setattr(google, 'google_request', deleted)
    assert routes.sync(user, db) == {'added': 0, 'has_more': False}
    assert routes.status(user, db)['last_synced_at'] is not None
