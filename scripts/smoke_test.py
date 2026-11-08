#!/usr/bin/env python3
"""Run a non-destructive end-to-end smoke test with isolated temporary state.

Run from the project root after npm run build: .venv/bin/python scripts/smoke_test.py
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid

import httpx


def unused_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def main():
    with tempfile.TemporaryDirectory(prefix='sentinel-smoke-') as temp:
        ports = [unused_port() for _ in range(3)]
        intel_port, lock_port, gateway_port = ports
        env = os.environ.copy()
        for key in ('GRANITE_ENDPOINT', 'GRANITE_API_KEY', 'GRANITE_MODEL', 'DEMO_PIN_ALICE', 'DEMO_PIN_BOB', 'SENTINEL_DEVICE_SECRET'):
            env.pop(key, None)
        env.update(GRANITE_ENDPOINT='', GRANITE_API_KEY='', GRANITE_MODEL='', DEMO_PIN_ALICE='1111', DEMO_PIN_BOB='2222', SENTINEL_DATA_DIR=os.path.join(temp, 'no-datasets'), SENTINEL_DB_PATH=os.path.join(temp, 'analysis.duckdb'), SENTINEL_INTERLOCK_DB=os.path.join(temp, 'interlock.sqlite3'), SENTINEL_INTERLOCK_MODE='demo', SENTINEL_INTELLIGENCE_PORT=str(intel_port), SENTINEL_INTERLOCK_PORT=str(lock_port))
        processes = []
        try:
            for module, port in [('app.main:app', intel_port), ('app.approval_service:app', lock_port), ('app.gateway:app', gateway_port)]:
                processes.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', module, '--host', '127.0.0.1', '--port', str(port), '--log-level', 'warning'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            base = f'http://127.0.0.1:{gateway_port}'
            with httpx.Client(base_url=base, timeout=20, trust_env=False) as client:
                for _ in range(100):
                    try:
                        if client.get('/api/health').status_code == 200 and client.get('/api/interlock/status').status_code == 200:
                            break
                    except httpx.RequestError:
                        pass
                    time.sleep(.1)
                else:
                    raise AssertionError('Services did not become ready')
                assert httpx.get(f'http://127.0.0.1:{intel_port}/api/interlock/status', timeout=5, trust_env=False).status_code == 404
                assert client.get('/').status_code == 200
                assert client.get('/manus-routes.json').json()['routes'][0]['path'] == '/'
                overview = client.get('/api/overview').json()
                assert overview['mode'] == 'deterministic-demo' and overview['stats']['total'] > 0
                records = client.get('/api/vulnerabilities', params={'limit': 2}).json()['items']
                assert records and records[0]['id'].startswith('DEMO-')
                record = records[0]['id']
                assert client.get(f'/api/vulnerabilities/{record}').status_code == 200
                assert client.get(f'/api/momentum/{record}').status_code == 200
                assert client.get('/api/profiles').status_code == 200
                assert client.get('/api/data-quality').status_code == 200
                assert client.get('/api/model').status_code == 200
                inquiry = client.post('/api/investigate', json={'question': f'Investigate {record}, exploitation momentum and simulated mission assurance', 'cve': record})
                assert inquiry.status_code == 200, inquiry.text
                assert len(inquiry.json()['agents']) >= 3
                operation = client.post('/api/interlock/propose', json={'action': 'Smoke test simulated operation'}).json()
                session_id = operation['session_id']
                def human(identity, pin, event='approve', sid=session_id, nonce=None):
                    return client.post(f'/api/interlock/{event}', json={'identity': identity, 'pin': pin, 'session_id': sid, 'nonce': nonce or uuid.uuid4().hex})
                assert operation['state'] == 'review_required'
                assert client.post('/api/interlock/approve', json={'identity': 'Alice', 'pin': '1111'}).status_code == 422
                assert human('Alice', 'bad').status_code == 403
                nonce = uuid.uuid4().hex
                assert human('Alice', '1111', nonce=nonce).json()['state'] == 'review_required'
                assert human('Alice', '1111', nonce=nonce).status_code == 409
                assert human('Alice', '1111').status_code == 409
                assert human('Bob', '2222').json()['state'] == 'approved'
                disconnected = client.post('/api/interlock/device', json={'connected': False}).json()
                assert disconnected['state'] == 'review_required' and not disconnected['approvals']
                assert human('Bob', '2222').status_code == 409
                client.post('/api/interlock/device', json={'connected': True})
                assert human('Alice', '1111', event='reject').json()['state'] == 'rejected'
                next_op = client.post('/api/interlock/propose', json={'action': 'Second smoke test'}).json()
                assert next_op['session_id'] != session_id
                assert human('Bob', '2222', sid=session_id).status_code == 409
                processes[1].terminate()
                processes[1].wait(timeout=5)
                unavailable = client.get('/api/interlock/status')
                assert unavailable.status_code == 503 and 'held' in unavailable.text
                print('PASS: data, investigation, route manifest, separate service routing, distinct approvals, duplicate/replay rejection, disconnect invalidation and service outage.')
        finally:
            for proc in processes:
                if proc.poll() is None:
                    proc.terminate()
            for proc in processes:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()


if __name__ == '__main__':
    main()
