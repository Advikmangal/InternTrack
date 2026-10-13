import csv
import io
from datetime import timedelta
from pypdf import PdfWriter
from app.models import now
from app.services import CSV_FIELDS
from .conftest import register, application


def test_auth_csrf_logout(clients):
    c,b = clients
    assert c.get('/api/applications').status_code == 401
    register(c)
    cookie = c.cookies.get('interntrack_session')
    assert cookie
    assert c.post('/api/auth/register', json={'name':'Alice','email':'alice@example.com','password':'local-test-password'}).status_code == 409
    assert c.get('/api/auth/me').json()['name'] == 'Alice'
    assert c.post('/api/applications', json={'company':'A','role':'B'}, headers={'X-CSRF-Token':''}).status_code == 403
    assert c.post('/api/applications', json={'company':'A','role':'B'}, headers={'Origin':'https://evil.example'}).status_code == 403
    assert c.post('/api/auth/logout').status_code == 204
    assert c.get('/api/auth/me').status_code == 401
    b.cookies.set('interntrack_session',cookie)
    assert b.get('/api/auth/me').status_code == 401
    assert c.post('/api/auth/login',json={'email':'alice@example.com','password':'wrong'}).status_code == 401
    login=c.post('/api/auth/login',json={'email':'alice@example.com','password':'local-test-password'})
    assert login.status_code == 200
    assert 'HttpOnly' in login.headers['set-cookie'] and 'SameSite=lax' in login.headers['set-cookie']


def test_app_crud_filter_history_and_isolation(clients):
    c,b=clients
    register(c);register(b,'bob@example.com')
    a=application(c)
    application(c,company='Zebra',status='Saved',application_date=None,work_mode='Hybrid')
    assert c.get('/api/applications?q=acme&status=Applied&work_mode=Remote&date_from=2026-10-01&date_to=2026-10-02').json()['total']==1
    assert c.get('/api/applications?page_size=1&page=2&sort=company').json()['items'][0]['company']=='Zebra'
    assert c.get('/api/applications?status=Offer').json()['total']==0
    assert b.get('/api/applications').json()['total']==0
    for method in ('get','put','delete'):
        kwargs={'json':{'company':'Hacked','role':'X'}} if method=='put' else {}
        assert getattr(b,method)(f"/api/applications/{a['id']}",**kwargs).status_code==404
    assert c.patch(f"/api/applications/{a['id']}/status",json={'status':'Interview'}).status_code==200
    c.patch(f"/api/applications/{a['id']}/status",json={'status':'Interview'})
    assert [h['status'] for h in c.get(f"/api/applications/{a['id']}").json()['history']]==['Applied','Interview']
    assert c.put(f"/api/applications/{a['id']}",json={'company':'Acme Updated','role':'Backend','status':'Offer','application_date':'2026-10-01'}).status_code==200
    assert c.get('/api/dashboard').json()['offers']==1
    assert c.delete(f"/api/applications/{a['id']}").status_code==204
    assert c.get(f"/api/applications/{a['id']}").status_code==404


def test_validation_and_dashboard(clients):
    c,_=clients;register(c)
    for values in [{'status':'Applied'},{'company':''},{'job_url':'javascript:alert(1)'},{'recruiter_email':'invalid'}]:
        assert c.post('/api/applications',json={'company':'A','role':'B',**values}).status_code==422
    for status in ['Saved','Applied','Assessment','Interview','Offer','Rejected','Withdrawn']:
        application(c,status=status,application_date=None if status=='Saved' else '2026-10-01')
    d=c.get('/api/dashboard').json()
    assert (d['submitted'],d['active'],d['offers'])==(6,3,1)
    assert d['timeline']=={'2026-10-01':6}
    assert sum(d['distribution'].values())==7
    assert c.get('/api/applications?group=active').json()['total']==3
    assert c.get('/api/applications?group=submitted').json()['total']==6


def test_interviews_and_followups(clients):
    c,b=clients;register(c);register(b,'bob@example.com');a=application(c)
    data={'title':'Round one','type':'Online','starts_at':(now()+timedelta(days=2)).isoformat(),'timezone':'Asia/Kolkata','venue':'Video call'}
    url=f"/api/applications/{a['id']}"
    assert b.post(url+'/interviews',json=data).status_code==404
    assert c.post(url+'/interviews',json={**data,'starts_at':'2026-10-14T10:00:00'}).status_code==422
    i=c.post(url+'/interviews',json=data).json()
    assert c.get('/api/dashboard').json()['upcoming_interviews']==1
    assert b.put(f"/api/interviews/{i['id']}",json=data).status_code==404
    assert c.put(f"/api/interviews/{i['id']}",json={**data,'outcome':'Progressed'}).json()['outcome']=='Progressed'
    assert len(c.get('/api/interviews?upcoming=true').json())==1
    assert b.get('/api/interviews').json()==[]
    f=c.post(url+'/follow-ups',json={'due_date':(now().date()-timedelta(days=2)).isoformat()}).json()
    assert c.get('/api/dashboard').json()['overdue_followups']==1
    assert b.post(f"/api/follow-ups/{f['id']}/complete",json={}).status_code==404
    assert c.put(f"/api/follow-ups/{f['id']}",json={'due_date':now().date().isoformat()}).status_code==200
    assert c.get('/api/follow-ups').json()[0]['bucket']=='today'
    assert c.post(f"/api/follow-ups/{f['id']}/complete",json={'next_date':(now().date()+timedelta(days=3)).isoformat()}).status_code==200
    assert c.post(f"/api/follow-ups/{f['id']}/complete",json={}).status_code==409
    assert c.get('/api/dashboard').json()['upcoming_followups']==1
    assert c.delete(f"/api/interviews/{i['id']}").status_code==204
    assert c.delete(url).status_code==204
    assert c.get('/api/follow-ups').json()==[]


def pdf():
    stream=io.BytesIO();w=PdfWriter();w.add_blank_page(width=100,height=100);w.write(stream);return stream.getvalue()


def test_private_uploads_and_associations(clients):
    c,b=clients;register(c);register(b,'bob@example.com')
    for filename,content in [('fake.pdf',b'%PDF- bad content'),('resume.txt',pdf()),('fake.pdf',b'<html>not pdf</html>')]:
        assert c.post('/api/resumes',data={'name':'Resume'},files={'file':(filename,content)}).status_code==422
    assert c.post('/api/resumes',data={'name':'Large'},files={'file':('big.pdf',b'x'*(5*1024*1024+1))}).status_code==413
    r=c.post('/api/resumes',data={'name':'Backend'},files={'file':('resume.pdf',pdf())})
    assert r.status_code==201,r.text
    rid=r.json()['id']
    assert 'filename' not in r.json()
    assert b.get(f'/api/resumes/{rid}/download').status_code==404
    assert b.delete(f'/api/resumes/{rid}').status_code==404
    assert b.post('/api/applications',json={'company':'A','role':'B','resume_id':rid}).status_code==404
    downloaded=c.get(f'/api/resumes/{rid}/download')
    assert downloaded.content==pdf() and 'attachment' in downloaded.headers['content-disposition']
    a=application(c,resume_id=rid)
    assert c.delete(f'/api/resumes/{rid}').status_code==204
    assert c.get(f"/api/applications/{a['id']}").json()['resume_id'] is None
    assert c.get(f'/api/resumes/{rid}/download').status_code==404


def test_attach_replace_and_detach_resume(clients):
    c, other = clients
    register(c)
    register(other, 'bob@example.com')
    app = application(c, notes='Keep these notes', salary='Paid')
    foreign_app = application(other)
    resumes = [c.post('/api/resumes', data={'name': name},
                     files={'file': ('resume.pdf', pdf())}).json()['id']
               for name in ('First version', 'Updated version')]
    url = f"/api/applications/{app['id']}/resume"
    original = c.get(f"/api/applications/{app['id']}").json()
    assert other.patch(url, json={'resume_id': None}).status_code == 404
    assert other.patch(f"/api/applications/{foreign_app['id']}/resume",
                       json={'resume_id': resumes[0]}).status_code == 404
    assert c.patch(url, json={}).status_code == 422
    assert c.patch(url, json={'resume_id': 0}).status_code == 422
    assert c.patch(url, json={'resume_id': 999999}).status_code == 404
    for resume_id in [*resumes, None]:
        result = c.patch(url, json={'resume_id': resume_id})
        assert result.status_code == 200, result.text
        current = c.get(f"/api/applications/{app['id']}").json()
        assert current['resume_id'] == resume_id
        for field in ('company', 'role', 'notes', 'salary', 'status', 'history'):
            assert current[field] == original[field]
    for resume_id in resumes:
        assert c.get(f'/api/resumes/{resume_id}/download').status_code == 200


def csv_text(rows):
    out=io.StringIO();w=csv.DictWriter(out,fieldnames=CSV_FIELDS);w.writeheader();w.writerows(rows);return out.getvalue()


def test_csv_preview_import_errors_duplicates_and_export(clients):
    c,b=clients;register(c);register(b,'bob@example.com')
    row={'company':'Acme','role':'Intern','status':'Applied','application_date':'2026-10-01','work_mode':'Remote'}
    data={'text':csv_text([row,{**row,'company':'acme'}])}
    p=c.post('/api/applications/import/preview',json=data).json()
    assert p['ready']==1 and 'duplicate' in p['rows'][1]['result']
    assert c.get('/api/applications').json()['total']==0
    assert c.post('/api/applications/import',json=data).json()=={'imported':1,'skipped':1}
    assert c.post('/api/applications/import',json=data).json()['imported']==0
    invalid={'text':csv_text([row,{**row,'company':'Bad','status':'Unknown'}])}
    p=c.post('/api/applications/import/preview',json=invalid).json()
    assert p['has_errors'] and p['rows'][1]['row']==3
    assert c.post('/api/applications/import',json=invalid).status_code==422
    assert c.post('/api/applications/import/preview',json={'text':'wrong,headers\na,b'}).status_code==422
    application(c,company='=HYPERLINK("bad")')
    assert "'=HYPERLINK" in c.get('/api/applications/export').text
    assert len(list(csv.DictReader(io.StringIO(b.get('/api/applications/export').text))))==0
    assert c.get('/api/applications/template').status_code==200


def test_settings_and_frontend_assets(clients):
    c,_=clients;register(c)
    assert c.patch('/api/auth/me',json={'name':'Alice','timezone':'No/Such_Zone'}).status_code==422
    assert c.patch('/api/auth/me',json={'name':'Alicia','timezone':'Asia/Kolkata'}).json()['name']=='Alicia'
    response=c.get('/')
    assert response.status_code==200 and 'InternTrack' in response.text
    assert "frame-ancestors 'none'" in response.headers['content-security-policy']
    assert c.get('/static/app.js').status_code==200
    assert c.get('/static/vendor/chart.umd.js').status_code==200
    assert c.get('/docs').status_code==200
    assert c.get('/static/vendor/swagger-ui-bundle.js').status_code==200
    assert '/api/applications/{app_id}/status' in c.get('/openapi.json').json()['paths']


def test_settings_timezone_validation_and_recovery(clients, monkeypatch):
    c, _ = clients
    original = register(c)
    for zone in ('ASIA', 'Asia', '', '../Asia', 'Not/AZone'):
        response = c.patch('/api/auth/me', json={'name': 'Changed', 'timezone': zone})
        assert response.status_code == 422, response.text
        assert response.json()['details'][0]['field'] == 'timezone'
        assert c.get('/api/auth/me').json()['name'] == original['name']
    # Reproduce the Windows directory-read failure on every test platform.
    from app import schemas
    def unreadable_zone(value):
        raise PermissionError('Cannot read timezone directory')
    with monkeypatch.context() as patch:
        patch.setattr(schemas, 'ZoneInfo', unreadable_zone)
        response = c.patch('/api/auth/me', json={'name': 'Changed', 'timezone': 'ASIA'})
        assert response.status_code == 422
        assert 'Asia/Kolkata' in response.json()['details'][0]['message']
    response = c.patch('/api/auth/me', json={'name': 'Alice', 'timezone': ' Asia/Kolkata '})
    assert response.status_code == 200
    assert response.json()['timezone'] == 'Asia/Kolkata'
    assert c.get('/api/auth/me').json()['timezone'] == 'Asia/Kolkata'


def test_error_pages_and_api_errors(clients, monkeypatch):
    c, _ = clients
    page = c.get('/not-a-real-page', headers={'Accept': 'text/html'})
    assert page.status_code == 404
    assert 'text/html' in page.headers['content-type']
    assert 'A wrong turn. Not a dead end.' in page.text
    assert 'href="/#dashboard"' in page.text
    assert '{{' not in page.text
    assert "frame-ancestors 'none'" in page.headers['content-security-policy']
    api_error = c.get('/api/not-a-real-endpoint', headers={'Accept': 'text/html'})
    assert api_error.status_code == 404
    assert api_error.json()['error'] == 'Not Found'
    unauthorized = c.get('/api/applications', headers={'Accept': 'text/html'})
    assert unauthorized.status_code == 401
    assert 'error' in unauthorized.json()
    register(c)
    from app.routers import authentication
    def fail_profile(*args):
        raise RuntimeError('private diagnostic must not reach browser')
    monkeypatch.setattr(authentication, 'profile', fail_profile)
    failure = c.get('/api/auth/me')
    assert failure.status_code == 500
    assert 'Please try again' in failure.json()['error']
    assert 'private diagnostic' not in failure.text
    assert failure.headers['cache-control'] == 'no-store'
    # Exercise HTML 500 rendering through a real browser-facing route.
    from app import main
    def fail_file(*args):
        raise RuntimeError('private file diagnostic')
    monkeypatch.setattr(main, 'FileResponse', fail_file)
    failure = c.get('/', headers={'Accept': 'text/html'})
    assert failure.status_code == 500
    assert 'A pause in the process.' in failure.text
    assert 'private file diagnostic' not in failure.text


def test_password_whitespace_and_session_expiry(clients):
    from app.database import get_db
    from app.main import app
    from app.models import Session
    from sqlalchemy import select
    c,_=clients
    password='  significant-spaces  '
    response=c.post('/api/auth/register',json={'name':'Space Test','email':'spaces@example.com','password':password})
    assert response.status_code==201
    c.headers['X-CSRF-Token']=response.json()['csrf']
    c.post('/api/auth/logout')
    assert c.post('/api/auth/login',json={'email':'spaces@example.com','password':password.strip()}).status_code==401
    assert c.post('/api/auth/login',json={'email':'spaces@example.com','password':password}).status_code==200
    database=app.dependency_overrides[get_db]()
    db=next(database)
    session=db.scalar(select(Session))
    session.expires_at=now()-timedelta(minutes=1)
    db.commit()
    database.close()
    assert c.get('/api/auth/me').status_code==401
