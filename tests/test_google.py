import pytest
from datetime import timedelta
from urllib.parse import urlparse, parse_qs
from sqlalchemy import select
from fastapi import HTTPException
from app import google
from app.config import settings
from app.database import get_db
from app.main import app
from app.models import GoogleAccount, GoogleOAuthState, EmailCandidate, now
from tests.conftest import register, application


class TestCipher:
    """Only for mocked provider tests; encryption gets its own real-library test."""
    def encrypt(self, value):
        return b'test-encrypted:' + value


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(settings, 'google_client_id', 'test-client')
    monkeypatch.setattr(settings, 'google_client_secret', 'test-secret')
    monkeypatch.setattr(settings, 'google_token_key', 'test-key')
    monkeypatch.setattr(google, 'cipher', lambda: TestCipher())
    state = {'email': 'alice@example.com', 'sub': 'google-alice', 'scope': google.GMAIL_SCOPE, 'verified': True, 'calls': []}
    def request(method, url, **kwargs):
        state['calls'].append((method, url, kwargs))
        if url == google.TOKEN_URL:
            return {'access_token': 'access', 'refresh_token': 'refresh', 'scope': state['scope']}
        if url.endswith('/userinfo'):
            return {'email': state['email'], 'email_verified': state['verified'], 'sub': state['sub'], 'name': 'Alice'}
        raise AssertionError(url)
    monkeypatch.setattr(google, 'google_request', request)
    return state


def start(client, connect=False):
    result = client.post('/api/google/connect') if connect else client.get('/api/google/login', follow_redirects=False)
    url = result.json()['url'] if connect else result.headers['location']
    return parse_qs(urlparse(url).query)


def callback(client, query, **params):
    return client.get('/api/google/callback', params={'state': query['state'][0], 'code': 'code', **params}, follow_redirects=False)


def test_google_signup_and_repeat_login(clients, provider):
    client, _ = clients
    query = start(client)
    assert query['code_challenge_method'] == ['S256']
    assert google.GMAIL_SCOPE not in query['scope'][0]
    result = callback(client, query)
    assert 'signed_in' in result.headers['location']
    me = client.get('/api/auth/me').json()
    assert me['email'] == 'alice@example.com'
    client.headers['X-CSRF-Token'] = me['csrf']
    assert client.get('/api/google/status').json()['connected'] is False
    client.post('/api/auth/logout')
    callback(client, start(client))
    assert client.get('/api/auth/me').json()['id'] == me['id']
    token_call = provider['calls'][0][2]['data']
    assert google.challenge(token_call['code_verifier']) == query['code_challenge'][0]


def test_state_is_browser_bound_one_time_and_denial_consumes(clients, provider):
    first, second = clients
    query = start(first)
    assert 'invalid_state' in callback(second, query).headers['location']
    assert not provider['calls']
    assert 'cancelled' in callback(first, query, error='access_denied').headers['location']
    assert 'invalid_state' in callback(first, query).headers['location']
    assert not provider['calls']


def test_expired_state(clients, provider):
    first, _ = clients
    query = start(first)
    with next(app.dependency_overrides[get_db]()) as db:
        flow = db.scalar(select(GoogleOAuthState))
        flow.expires_at = now() - timedelta(minutes=1)
        db.commit()
    assert 'invalid_state' in callback(first, query).headers['location']
    assert not provider['calls']


def test_existing_account_requires_authenticated_link(clients, provider):
    first, second = clients
    original = register(first)
    assert 'link_required' in callback(second, start(second)).headers['location']
    assert second.get('/api/auth/me').status_code == 401
    query = start(first, connect=True)
    assert query['access_type'] == ['offline']
    assert 'connected' in callback(first, query).headers['location']
    with next(app.dependency_overrides[get_db]()) as db:
        stored = db.get(GoogleAccount, original['id'])
        assert stored.refresh_token != 'refresh'
    assert 'signed_in' in callback(second, start(second)).headers['location']
    assert second.get('/api/auth/me').json()['id'] == original['id']


def test_wrong_account_scope_and_unverified_email(clients, provider):
    first, _ = clients
    register(first)
    provider['email'] = 'other@example.com'
    assert 'wrong_account' in callback(first, start(first, True)).headers['location']
    provider['email'] = 'alice@example.com'
    provider['scope'] = 'openid email'
    assert 'missing_permission' in callback(first, start(first, True)).headers['location']
    provider['verified'] = False
    assert 'failed' in callback(first, start(first, True)).headers['location']
    assert first.get('/api/google/status').json()['connected'] is False


def test_connect_requires_csrf_and_same_session(clients, provider):
    first, _ = clients
    assert first.post('/api/google/connect').status_code == 401
    register(first)
    csrf = first.headers.pop('X-CSRF-Token')
    assert first.post('/api/google/connect').status_code == 403
    first.headers['X-CSRF-Token'] = csrf
    query = start(first, True)
    first.post('/api/auth/logout')
    assert 'failed' in callback(first, query).headers['location']
    assert not provider['calls']


@pytest.mark.parametrize('subject,snippet,expected', [
    ('You applied for Backend Intern at Acme', '', 'Applied'),
    ('Application received', 'Thank you for your application', 'Applied'),
    ('Interview invitation', 'Interview scheduled for tomorrow', 'Interview'),
    ('Update on your application', 'Unfortunately, we are not moving forward', 'Rejected'),
    ('Complete your coding assessment', '', 'Assessment'),
    ('Job offer', 'We are pleased to offer you a position', 'Offer'),
    ('Recommended jobs', 'You applied for a job last week', None),
    ('Job alert: new roles', 'Application received', None),
    ('Weekly newsletter', 'Hello', None),
])
def test_classification(subject, snippet, expected):
    result = google.classify(subject, snippet)
    assert (result['suggested_status'] if result else None) == expected


def connect_account(client):
    register(client)
    assert 'connected' in callback(client, start(client, True)).headers['location']


def test_sync_pagination_dedup_review_ownership_disconnect(clients, provider, monkeypatch):
    first, second = clients
    connect_account(first)
    register(second, 'bob@example.com')
    monkeypatch.setattr(google, 'access_token', lambda account: 'access')
    calls = []
    def gmail(method, url, **kwargs):
        calls.append(kwargs)
        if url.endswith('/messages'):
            page2 = kwargs['params'].get('pageToken') == 'page2'
            return {'messages': [{'id': 'one'}, {'id': 'two'}] if page2 else [{'id': 'one'}], **({} if page2 else {'nextPageToken': 'page2'})}
        return {'payload': {'headers': [{'name': 'Subject', 'value': 'You applied for Backend Intern at Acme'}, {'name': 'From', 'value': 'Indeed <noreply@indeed.com>'}]},
                'snippet': '<script>untrusted</script> Application received', 'internalDate': '1793000000000'}
    monkeypatch.setattr(google, 'google_request', gmail)
    assert first.post('/api/google/sync').json() == {'added': 1, 'has_more': True}
    assert first.post('/api/google/sync').json() == {'added': 1, 'has_more': False}
    queue = first.get('/api/google/emails').json()
    assert queue['total'] == 2
    assert second.get('/api/google/emails').json()['total'] == 0
    item = queue['items'][0]
    assert item['company'] == 'Acme'
    assert item['role'] == 'Backend Intern'
    assert second.post(f"/api/google/emails/{item['id']}/dismiss").status_code == 404
    foreign = application(second)
    assert first.post(f"/api/google/emails/{item['id']}/import", json={'application_id': foreign['id']}).status_code == 404
    imported = first.post(f"/api/google/emails/{item['id']}/import", json={'company': 'Acme', 'role': 'Backend Intern', 'status': 'Applied'})
    assert imported.status_code == 200, imported.text
    assert first.post(f"/api/google/emails/{item['id']}/import", json={'company': 'Acme', 'role': 'Backend Intern'}).status_code == 409
    other = queue['items'][1]
    assert first.post(f"/api/google/emails/{other['id']}/import", json={'company': 'Acme', 'role': 'Backend Intern'}).status_code == 409
    app_id = imported.json()['application_id']
    assert first.post(f"/api/google/emails/{other['id']}/import", json={'application_id': app_id, 'status': 'Interview'}).status_code == 200
    record = first.get(f'/api/applications/{app_id}').json()
    assert record['status'] == 'Interview'
    assert [h['status'] for h in record['history']] == ['Applied', 'Interview']
    assert first.post('/api/google/disconnect').status_code == 204
    assert first.get('/api/google/emails').json()['total'] == 0
    assert first.get('/api/google/status').json()['linked'] is True
    assert first.post('/api/google/sync').status_code == 409
    assert first.get(f'/api/applications/{app_id}').status_code == 200


def test_failed_sync_does_not_advance_cursor(clients, provider, monkeypatch):
    first, _ = clients
    connect_account(first)
    monkeypatch.setattr(google, 'access_token', lambda account: 'access')
    def fail(method, url, **kwargs):
        if url.endswith('/messages'):
            return {'messages': [{'id': 'one'}], 'nextPageToken': 'page2'}
        raise HTTPException(502, 'Google unavailable')
    monkeypatch.setattr(google, 'google_request', fail)
    assert first.post('/api/google/sync').status_code == 502
    connection = first.get('/api/google/status').json()
    assert connection['last_synced_at'] is None
    assert connection['has_more'] is False
    assert first.get('/api/google/emails').json()['total'] == 0


def test_real_token_encryption(monkeypatch):
    fernet = pytest.importorskip('cryptography.fernet', reason='cryptography download unavailable in this environment')
    monkeypatch.setattr(settings, 'google_token_key', fernet.Fernet.generate_key().decode())
    encrypted = google.cipher().encrypt(b'refresh-token')
    assert b'refresh-token' not in encrypted
    assert google.cipher().decrypt(encrypted) == b'refresh-token'
    monkeypatch.setattr(settings, 'google_token_key', 'invalid')
    with pytest.raises(HTTPException):
        google.cipher()


def test_real_token_refresh_and_invalid_key(monkeypatch):
    from types import SimpleNamespace
    fernet = pytest.importorskip('cryptography.fernet')
    monkeypatch.setattr(settings, 'google_token_key', fernet.Fernet.generate_key().decode())
    account = SimpleNamespace(refresh_token=google.cipher().encrypt(b'old-refresh').decode())
    def exchange(method, url, **kwargs):
        assert kwargs['data']['refresh_token'] == 'old-refresh'
        assert kwargs['data']['grant_type'] == 'refresh_token'
        return {'access_token': 'access', 'refresh_token': 'new-refresh'}
    monkeypatch.setattr(google, 'google_request', exchange)
    assert google.access_token(account) == 'access'
    assert google.cipher().decrypt(account.refresh_token.encode()) == b'new-refresh'
    monkeypatch.setattr(settings, 'google_token_key', fernet.Fernet.generate_key().decode())
    with pytest.raises(HTTPException) as err:
        google.access_token(account)
    assert err.value.status_code == 409
