import time
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.auth import sign_session, SESSION_SECONDS

SECRET = 'test-only-workspace-access-code-123456789'


def test_hosted_access_cookie_and_bearer(tmp_path, monkeypatch):
    monkeypatch.setenv('WAYPOINT_ACCESS_TOKEN', SECRET)
    monkeypatch.setenv('WAYPOINT_REQUIRE_AUTH', '1')
    with TestClient(create_app(tmp_path), base_url='https://testserver') as client:
        assert client.get('/api/health').json()['auth_required'] is True
        assert client.get('/api/workspace').status_code == 401
        assert client.post('/api/reset', json={}).status_code == 401
        assert client.post('/api/auth', json={'access_code':'wrong'}).status_code == 401
        assert client.post('/api/auth', json={'access_code':'不正确'}).status_code == 401
        result = client.post('/api/auth', json={'access_code':SECRET})
        assert result.status_code == 200
        assert 'HttpOnly' in result.headers['set-cookie']
        assert 'Secure' in result.headers['set-cookie']
        assert 'SameSite=strict' in result.headers['set-cookie']
        assert SECRET not in result.headers['set-cookie']
        assert client.get('/api/workspace').status_code == 200
        assert client.post('/api/logout', json={}).status_code == 200
        assert client.get('/api/workspace').status_code == 401
        assert client.get('/api/workspace', headers={'Authorization':f'Bearer {SECRET}'}).status_code == 200


def test_expired_and_tampered_sessions_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv('WAYPOINT_ACCESS_TOKEN', SECRET)
    with TestClient(create_app(tmp_path)) as client:
        for token in ('bad',sign_session(SECRET, int(time.time())-SESSION_SECONDS-1),sign_session('different-secret')):
            client.cookies.set('waypoint_session',token)
            assert client.get('/api/workspace').status_code == 401


def test_login_attempts_rate_limited(tmp_path, monkeypatch):
    monkeypatch.setenv('WAYPOINT_ACCESS_TOKEN', SECRET)
    with TestClient(create_app(tmp_path)) as client:
        for _ in range(10):
            assert client.post('/api/auth', json={'access_code':'wrong'}).status_code == 401
        assert client.post('/api/auth', json={'access_code':'wrong'}).status_code == 429


def test_concurrent_approvals_apply_exactly_once(tmp_path, monkeypatch):
    monkeypatch.delenv('WAYPOINT_ACCESS_TOKEN',raising=False)
    monkeypatch.delenv('WAYPOINT_MODEL',raising=False)
    with TestClient(create_app(tmp_path)) as client:
        plan = client.post('/api/plans',json={}).json()
        with ThreadPoolExecutor(max_workers=8) as pool:
            codes = list(pool.map(lambda _:client.post(f"/api/plans/{plan['id']}/decision",json={'approved':True}).status_code,range(8)))
        assert codes.count(200) == 1
        assert codes.count(409) == 7
        assert client.get('/api/workspace').json()['revision'] == 1


def test_concurrent_ticks_have_no_lost_updates(tmp_path, monkeypatch):
    monkeypatch.delenv('WAYPOINT_ACCESS_TOKEN',raising=False)
    with TestClient(create_app(tmp_path)) as client:
        with ThreadPoolExecutor(max_workers=16) as pool:
            codes=list(pool.map(lambda _:client.post('/api/advance',json={'ticks':1}).status_code,range(64)))
        assert all(c==200 for c in codes)
        assert client.get('/api/workspace').json()['tick']==64
