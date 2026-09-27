from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.simulation import SHELVES, RACKS, DOCKS, fresh, tick, route, compare, set_incident


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("WAYPOINT_MODEL", raising=False)
    with TestClient(create_app(tmp_path)) as client:
        yield client


def test_all_shelves_remain_reachable_with_closure():
    state = fresh()
    set_incident(state, True)
    walls = set(map(tuple, RACKS + [tuple(p) for p in state['blocked']]))
    for shelf in SHELVES.values():
        for dock in DOCKS:
            path = route(shelf, dock, state['blocked'])
            assert path is not None
            previous = shelf
            for cell in path:
                assert tuple(cell) not in walls
                assert abs(cell[0]-previous[0])+abs(cell[1]-previous[1]) == 1
                previous = cell


def test_wave_completes_without_duplicate_assignments():
    state = fresh()
    for _ in range(900):
        tick(state)
        active = [r['order'] for r in state['robots'] if r['order']]
        assert len(active) == len(set(active))
    assert all(o['status'] == 'complete' for o in state['orders'])
    assert all(o['completed_tick'] > o['started_tick'] for o in state['orders'])


def test_comparison_does_not_mutate_live_state():
    state = tick(fresh(), 12)
    original = deepcopy(state)
    results = compare(state)
    assert state == original
    assert len(results) == 3
    assert results == compare(state)
    assert results[1]['newly_completed'] > results[0]['newly_completed']


def test_api_approval_applies_once(client):
    response = client.post('/api/plans', json={'objective': 'throughput'})
    assert response.status_code == 200
    plan = response.json()
    assert plan['status'] == 'pending'
    assert client.get('/api/workspace').json()['policy'] == 'fifo'
    response = client.post(f"/api/plans/{plan['id']}/decision", json={'approved': True})
    assert response.status_code == 200
    assert response.json()['workspace']['policy'] == plan['recommendation']
    assert response.json()['run']['status'] == 'approved'
    assert client.post(f"/api/plans/{plan['id']}/decision", json={'approved': True}).status_code == 409


def test_rejection_preserves_policy(client):
    plan = client.post('/api/plans', json={}).json()
    result = client.post(f"/api/plans/{plan['id']}/decision", json={'approved': False}).json()
    assert result['run']['status'] == 'rejected'
    assert result['workspace']['policy'] == 'fifo'


@pytest.mark.parametrize('mutation,body',[('/api/reset',{}),('/api/incident',{'enabled':True})])
def test_stale_plan_cannot_apply(client, mutation, body):
    plan = client.post('/api/plans', json={}).json()
    assert client.post(mutation,json=body).status_code == 200
    assert client.post(f"/api/plans/{plan['id']}/decision", json={'approved':True}).status_code == 409


def test_csv_validates_and_imports_atomically(client):
    before = client.get('/api/workspace').json()
    invalid = b'order_id,shelf,priority,due_minutes,units\nO-1,Z9,urgent,10,2\n'
    assert client.post('/api/import',files={'file':('bad.csv',invalid)}).status_code == 422
    assert client.get('/api/workspace').json() == before
    valid = b'order_id,shelf,priority,due_minutes,units\nO-1,A1,urgent,10,2\nO-2,D4,standard,25,1\n'
    response = client.post('/api/import',files={'file':('wave.csv',valid)})
    assert response.status_code == 200
    state = response.json()
    assert state['metrics']['total'] == 2
    assert state['orders'][0]['due_tick'] == 60
    assert state['id'] != before['id']


@pytest.mark.parametrize('row',[
    'O1,A1,urgent,nan,1', 'O1,A1,urgent,10,-1', 'O1,A1,unknown,10,1',
    'O1,A1,urgent,10,1,extra', 'O1,A1,urgent,10', '=CMD,A1,urgent,10,1',
    'O1,A1,urgent,10,1\nO1,A2,urgent,10,1',
])
def test_bad_csv_rows(client, row):
    data = 'order_id,shelf,priority,due_minutes,units\n'+row+'\n'
    assert client.post('/api/import',files={'file':('bad.csv',data)}).status_code == 422


def test_bounds_and_foreign_origins(client):
    assert client.post('/api/advance',json={'ticks':61}).status_code == 422
    assert client.post('/api/advance',json={'ticks':0}).status_code == 422
    assert client.post('/api/plans',json={'objective':'invented'}).status_code == 422
    assert client.post('/api/import',files={'file':('large.csv',b'x'*256001)}).status_code == 413
    assert client.post('/api/reset',headers={'origin':'https://untrusted.example'}).status_code == 403


def test_pending_graph_resumes_after_process_restart(tmp_path, monkeypatch):
    monkeypatch.delenv('WAYPOINT_MODEL',raising=False)
    with TestClient(create_app(tmp_path)) as first:
        first.post('/api/advance',json={'ticks':20})
        plan = first.post('/api/plans',json={}).json()
    with TestClient(create_app(tmp_path)) as second:
        assert second.get('/api/workspace').json()['tick'] == 20
        assert second.get('/api/plans').json()[0]['id'] == plan['id']
        response = second.post(f"/api/plans/{plan['id']}/decision",json={'approved':True})
        assert response.status_code == 200
        assert response.json()['run']['status'] == 'approved'


def test_export_contains_evidence(client):
    client.post('/api/plans',json={})
    response = client.get('/api/export')
    assert response.status_code == 200
    report = response.json()
    assert len(report['plans']) == 1
    assert report['workspace']['metrics']['total'] == 48
    assert 'collision' in report['model_assumptions']
