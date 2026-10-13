import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from app.database import Base, get_db
from app.main import app
from app.config import settings


@pytest.fixture
def clients(tmp_path):
    url = os.getenv('TEST_DATABASE_URL')
    engine = create_engine(url) if url else create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    if not url:
        @event.listens_for(engine, 'connect')
        def fk(connection, record):
            connection.execute('PRAGMA foreign_keys=ON')
        Base.metadata.create_all(engine)
    connection = engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(bind=connection, expire_on_commit=False, join_transaction_mode='create_savepoint')
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    old_dir = settings.upload_dir
    settings.upload_dir = tmp_path
    with TestClient(app, headers={'Origin':'http://localhost:8000'}) as first, TestClient(app, headers={'Origin':'http://localhost:8000'}) as second:
        yield first, second
    app.dependency_overrides.clear()
    settings.upload_dir = old_dir
    transaction.rollback()
    connection.close()
    engine.dispose()


def register(client, email='alice@example.com'):
    result = client.post('/api/auth/register', json={'name':'Alice','email':email,'password':'local-test-password'})
    assert result.status_code == 201, result.text
    client.headers['X-CSRF-Token'] = result.json()['csrf']
    return result.json()


def application(client, **kwargs):
    data = {'company':'Acme', 'role':'Backend Intern', 'status':'Applied', 'application_date':'2026-10-01', **kwargs}
    result = client.post('/api/applications', json=data)
    assert result.status_code == 201, result.text
    return result.json()
