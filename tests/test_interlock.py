import hashlib
import hmac
import json
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import interlock


@pytest.fixture
def setup(monkeypatch, tmp_path):
    for name in ("DEMO_PIN_ALICE", "DEMO_PIN_BOB", "SENTINEL_DEVICE_SECRET",
                 "SENTINEL_INTERLOCK_MODE", "SENTINEL_INTERLOCK_TTL_SECONDS",
                 "SENTINEL_INTERLOCK_DEVICE_LEASE_SECONDS", "SENTINEL_INTERLOCK_CLOCK_SKEW_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SENTINEL_INTERLOCK_DB", str(tmp_path / "interlock.sqlite3"))
    clock = [1_800_000_000.0]
    monkeypatch.setattr(interlock.time, "time", lambda: clock[0])
    app = FastAPI()
    app.include_router(interlock.router)
    with TestClient(app) as client:
        yield client, clock, tmp_path


def propose(client):
    response = client.post("/api/interlock/propose", json={"action": "Simulate safe mission hold release"})
    assert response.status_code == 200, response.text
    return response.json()


def decision(client, identity, pin, event="approve", *, session_id=None, nonce=None):
    if session_id is None:
        session_id = getstatus(client)["session_id"] or "no-current-session"
    return client.post(f"/api/interlock/{event}", json={
        "identity": identity, "pin": pin, "session_id": session_id,
        "nonce": nonce if nonce is not None else str(uuid.uuid4()),
    })


def getstatus(client):
    response = client.get("/api/interlock/status")
    assert response.status_code == 200, response.text
    return response.json()


def test_demo_initial_contract_missing_approval_and_invalid_state(setup):
    client, _, _ = setup
    initial = getstatus(client)
    assert {"operation", "state", "approvals", "device_connected", "review_reason", "audit", "expires_at", "mode"} <= set(initial)
    assert initial["state"] == "idle" and initial["mode"] == "demo"
    assert initial["device_connected"] is True  # This is simulated, never a hardware check.
    assert decision(client, "Alice", "1111").status_code == 409
    state = propose(client)
    assert state["state"] == "review_required" and state["expires_at"]
    assert state["session_id"] and not state["approvals"]
    assert client.post("/api/interlock/propose", json={"action": "Other"}).status_code == 409
    first = decision(client, "Alice", "1111")
    assert first.status_code == 200
    assert first.json()["state"] == "review_required"  # one is not enough
    assert [a["identity"] for a in first.json()["approvals"]] == ["Alice"]
    second = decision(client, "Bob", "2222")
    assert second.status_code == 200 and second.json()["state"] == "approved"
    assert {a["identity"] for a in second.json()["approvals"]} == {"Alice", "Bob"}
    assert decision(client, "Bob", "2222").status_code == 409


def test_bad_pin_duplicate_credentials_and_audit_does_not_contain_secrets(setup, monkeypatch):
    client, _, _ = setup
    monkeypatch.setenv("DEMO_PIN_ALICE", "unique-alice-secret-8492")
    monkeypatch.setenv("DEMO_PIN_BOB", "unique-bob-secret-7520")
    propose(client)
    assert decision(client, "Alice", "wrong-secret-4278").status_code == 403
    assert decision(client, "Mallory", "unique-alice-secret-8492").status_code == 403
    assert decision(client, "Alice", "unique-alice-secret-8492").status_code == 200
    assert decision(client, "Alice", "unique-alice-secret-8492").status_code == 409
    s = getstatus(client)
    assert s["state"] == "review_required" and len(s["approvals"]) == 1
    audit = json.dumps(s["audit"])
    for secret in ("unique-alice-secret-8492", "unique-bob-secret-7520", "wrong-secret-4278"):
        assert secret not in audit
    assert "authentication_failed" in audit and "approval_denied" in audit


def test_disconnect_invalidates_one_or_both_and_reconnection_never_restores(setup):
    client, _, _ = setup
    propose(client)
    assert decision(client, "Alice", "1111").status_code == 200
    disconnected = client.post("/api/interlock/device", json={"connected": False}).json()
    assert not disconnected["device_connected"] and disconnected["approvals"] == []
    assert disconnected["state"] == "review_required"
    assert decision(client, "Bob", "2222").status_code == 409
    client.post("/api/interlock/device", json={"connected": True})
    assert decision(client, "Bob", "2222").json()["state"] == "review_required"
    assert decision(client, "Alice", "1111").json()["state"] == "approved"
    disconnected = client.post("/api/interlock/device", json={"connected": False}).json()
    assert disconnected["state"] == "review_required" and disconnected["approvals"] == []
    assert "approvals_invalidated" in [event["event"] for event in disconnected["audit"]]
    client.post("/api/interlock/device", json={"connected": True})
    assert getstatus(client)["state"] == "review_required"


def test_reject_validates_identity_and_clears_approval(setup):
    client, _, _ = setup
    propose(client)
    decision(client, "Alice", "1111")
    assert decision(client, "Bob", "bad", "reject").status_code == 403
    rejected = decision(client, "Bob", "2222", "reject")
    assert rejected.status_code == 200 and rejected.json()["state"] == "rejected"
    assert rejected.json()["approvals"] == []
    assert decision(client, "Bob", "2222").status_code == 409
    assert propose(client)["state"] == "review_required"


def test_session_expires_and_cannot_be_revived_by_reconnecting(setup):
    client, clock, _ = setup
    propose(client)
    decision(client, "Alice", "1111")
    assert decision(client, "Bob", "2222").json()["state"] == "approved"
    clock[0] += 300
    s = getstatus(client)
    assert s["state"] == "expired" and s["approvals"] == []
    assert decision(client, "Bob", "2222").status_code == 409
    client.post("/api/interlock/device", json={"connected": True})
    assert getstatus(client)["state"] == "expired"
    assert propose(client)["state"] == "review_required"


def test_state_and_audit_are_persistent_and_pins_are_not_stored(setup, monkeypatch):
    client, _, path = setup
    monkeypatch.setenv("DEMO_PIN_ALICE", "alpha-pin-8435684")
    propose(client)
    decision(client, "Alice", "alpha-pin-8435684")
    app2 = FastAPI()
    app2.include_router(interlock.router)
    with TestClient(app2) as other:
        assert len(getstatus(other)["approvals"]) == 1
        assert decision(other, "Bob", "2222").json()["state"] == "approved"
    with sqlite3.connect(path / "interlock.sqlite3") as db:
        dump = "\n".join(db.iterdump())
    assert "alpha-pin-8435684" not in dump and "2222" not in dump
    assert (path / "interlock.sqlite3").stat().st_mode & 0o077 == 0


def test_bad_demo_identity_configuration_fails_closed(setup, monkeypatch):
    client, _, _ = setup
    monkeypatch.setenv("DEMO_PIN_ALICE", "same")
    monkeypatch.setenv("DEMO_PIN_BOB", "same")
    propose(client)
    assert decision(client, "Alice", "same").status_code == 503
    assert getstatus(client)["state"] == "review_required"


def test_invalid_configuration_clears_existing_approvals(setup, monkeypatch):
    client, _, _ = setup
    propose(client)
    decision(client, "Alice", "1111")
    assert decision(client, "Bob", "2222").json()["state"] == "approved"
    monkeypatch.setenv("DEMO_PIN_ALICE", "same")
    monkeypatch.setenv("DEMO_PIN_BOB", "same")
    status = getstatus(client)
    assert status["state"] == "review_required" and status["approvals"] == []
    assert decision(client, "Alice", "same").status_code == 503


def test_simultaneous_duplicate_cannot_become_two_approvals(setup):
    client, _, _ = setup
    propose(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda _: decision(client, "Alice", "1111").status_code, range(2)))
    assert sorted(codes) == [200, 409]
    s = getstatus(client)
    assert s["state"] == "review_required" and len(s["approvals"]) == 1


@pytest.mark.parametrize("event", ["approve", "reject"])
def test_demo_requires_all_fields_and_consumes_nonce_on_invalid_body(setup, event):
    client, _, _ = setup
    session = propose(client)["session_id"]
    for missing in ("identity", "pin", "session_id", "nonce"):
        payload = {"identity": "Alice", "pin": "1111", "session_id": session, "nonce": str(uuid.uuid4())}
        invalid = {key: value for key, value in payload.items() if key != missing}
        assert client.post(f"/api/interlock/{event}", json=invalid).status_code == 422
        if missing != "nonce":
            # Even an incomplete body burns its otherwise valid nonce.
            assert client.post(f"/api/interlock/{event}", json=payload).status_code == 409
    for nonce in ("", "too-short", "!" * 36, 123, None):
        payload = {"identity": "Alice", "pin": "1111", "session_id": session, "nonce": nonce}
        assert client.post(f"/api/interlock/{event}", json=payload).status_code == 422
    for bad_session in ("", None, 123):
        payload = {"identity": "Alice", "pin": "1111", "session_id": bad_session, "nonce": str(uuid.uuid4())}
        assert client.post(f"/api/interlock/{event}", json=payload).status_code == 422
        payload["session_id"] = session
        assert client.post(f"/api/interlock/{event}", json=payload).status_code == 409
    assert getstatus(client)["state"] == "review_required" and not getstatus(client)["approvals"]


@pytest.mark.parametrize("field", ["identity", "pin", "session_id"])
def test_demo_invalid_unicode_still_consumes_nonce(setup, field):
    client, _, _ = setup
    session = propose(client)["session_id"]
    payload = {"identity": "Alice", "pin": "1111", "session_id": session, "nonce": str(uuid.uuid4())}
    invalid = dict(payload, **{field: "\ud800"})
    assert client.post("/api/interlock/approve", content=json.dumps(invalid),
                       headers={"Content-Type": "application/json"}).status_code == 422
    assert client.post("/api/interlock/approve", json=payload).status_code == 409
    assert not getstatus(client)["approvals"]


@pytest.mark.parametrize("event", ["approve", "reject"])
def test_demo_no_current_session_and_wrong_session_burn_nonce(setup, event):
    client, _, _ = setup
    no_session_nonce = str(uuid.uuid4())
    assert decision(client, "Alice", "1111", event, session_id="no-current-session", nonce=no_session_nonce).status_code == 409
    session = propose(client)["session_id"]
    # A request sent while idle cannot be made effective by changing its session.
    assert decision(client, "Alice", "1111", event, session_id=session, nonce=no_session_nonce).status_code == 409
    wrong_session_nonce = str(uuid.uuid4())
    assert decision(client, "Alice", "1111", event, session_id="wrong-session", nonce=wrong_session_nonce).status_code == 409
    assert decision(client, "Alice", "1111", event, session_id=session, nonce=wrong_session_nonce).status_code == 409
    assert getstatus(client)["state"] == "review_required" and not getstatus(client)["approvals"]


def test_demo_same_session_replays_and_denied_requests_consume_nonces(setup):
    client, _, _ = setup
    session = propose(client)["session_id"]
    bad_nonce = str(uuid.uuid4())
    assert decision(client, "Alice", "bad", session_id=session, nonce=bad_nonce).status_code == 403
    assert decision(client, "Alice", "1111", session_id=session, nonce=bad_nonce).status_code == 409

    approval_nonce = str(uuid.uuid4())
    assert decision(client, "Alice", "1111", session_id=session, nonce=approval_nonce).status_code == 200
    assert decision(client, "Alice", "1111", session_id=session, nonce=approval_nonce).status_code == 409
    # Nonces are shared between identities and between approval and rejection.
    assert decision(client, "Bob", "2222", session_id=session, nonce=approval_nonce).status_code == 409
    assert decision(client, "Bob", "2222", "reject", session_id=session, nonce=approval_nonce).status_code == 409
    assert len(getstatus(client)["approvals"]) == 1
    rejection_nonce = str(uuid.uuid4())
    assert decision(client, "Bob", "2222", "reject", session_id=session, nonce=rejection_nonce).status_code == 200
    assert decision(client, "Alice", "1111", session_id=session, nonce=rejection_nonce).status_code == 409


def test_demo_replay_across_operations_and_restart(setup):
    client, _, path = setup
    first_session = propose(client)["session_id"]
    approval_nonce, rejection_nonce, failed_nonce = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    assert decision(client, "Alice", "bad", session_id=first_session, nonce=failed_nonce).status_code == 403
    assert decision(client, "Alice", "1111", session_id=first_session, nonce=approval_nonce).status_code == 200
    assert decision(client, "Bob", "2222", "reject", session_id=first_session, nonce=rejection_nonce).status_code == 200
    second_session = propose(client)["session_id"]
    assert second_session != first_session
    app2 = FastAPI()
    app2.include_router(interlock.router)
    with TestClient(app2) as restarted:
        for who, pin, event, nonce in (("Alice", "1111", "approve", approval_nonce),
                                       ("Bob", "2222", "reject", rejection_nonce)):
            assert decision(restarted, who, pin, event, session_id=first_session, nonce=nonce).status_code == 409
            # Replacing the session ID must not turn a replay into a fresh decision.
            assert decision(restarted, who, pin, event, session_id=second_session, nonce=nonce).status_code == 409
        # A fresh nonce cannot make an old-session decision valid either.
        assert decision(restarted, "Alice", "1111", session_id=first_session).status_code == 409
        assert decision(restarted, "Alice", "1111", session_id=second_session, nonce=failed_nonce).status_code == 409
        state = getstatus(restarted)
        assert state["state"] == "review_required" and state["approvals"] == []
        assert decision(restarted, "Alice", "1111", session_id=second_session).status_code == 200
    with sqlite3.connect(path / "interlock.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM demo_nonces").fetchone()[0] == 5


def test_demo_nonce_consumption_is_atomic_for_concurrent_decisions(setup):
    client, _, _ = setup
    session = propose(client)["session_id"]
    nonce = str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda person: decision(client, *person, session_id=session, nonce=nonce).status_code,
                              (("Alice", "1111"), ("Bob", "2222"))))
    assert sorted(codes) == [200, 409]
    state = getstatus(client)
    assert state["state"] == "review_required" and len(state["approvals"]) == 1


def test_demo_storage_failure_cannot_approve(setup, monkeypatch):
    client, _, path = setup
    session = propose(client)["session_id"]
    monkeypatch.setenv("SENTINEL_INTERLOCK_DB", str(path))  # A directory cannot be opened as the database.
    assert decision(client, "Alice", "1111", session_id=session).status_code == 503
    monkeypatch.setenv("SENTINEL_INTERLOCK_DB", str(path / "interlock.sqlite3"))
    assert getstatus(client)["state"] == "review_required" and not getstatus(client)["approvals"]


@pytest.fixture
def wired(setup, monkeypatch):
    client, clock, path = setup
    secret = "wired-device-test-secret-with-more-than-32-bytes"
    monkeypatch.setenv("SENTINEL_INTERLOCK_MODE", "wired")
    monkeypatch.setenv("SENTINEL_DEVICE_SECRET", secret)
    monkeypatch.setenv("DEMO_PIN_ALICE", "human-alpha")
    monkeypatch.setenv("DEMO_PIN_BOB", "human-bravo")
    return client, clock, path, secret


def signed(client, secret, payload, signature=None):
    raw = json.dumps(payload, separators=(",", ":")).encode()
    sig = signature if signature is not None else hmac.new(secret.encode(), b"sentinel-interlock-v1\n" + raw, hashlib.sha256).hexdigest()
    return client.post("/api/interlock/device/event", content=raw, headers={"Content-Type": "application/json", "X-Interlock-Signature": sig})


def event(kind, clock, nonce, **extra):
    return {"event": kind, "timestamp": int(clock[0]), "nonce": nonce, **extra}


def test_wired_requires_auth_and_direct_demo_endpoints_are_disabled(wired, monkeypatch):
    client, clock, _, secret = wired
    assert getstatus(client)["device_connected"] is False
    assert client.post("/api/interlock/device", json={"connected": True}).status_code == 403
    p = propose(client)
    assert decision(client, "Alice", "human-alpha").status_code == 403
    assert decision(client, "Alice", "human-alpha", "reject").status_code == 403
    assert client.post("/api/interlock/approve", json={"identity": "Alice", "pin": "human-alpha"}).status_code == 403
    assert signed(client, secret, event("connect", clock, "N" * 20), signature="0" * 64).status_code == 403
    assert not getstatus(client)["device_connected"]
    assert signed(client, secret, event("connect", clock, "C" * 20)).status_code == 200
    approval = event("approve", clock, "A" * 20, session_id=p["session_id"], identity="Alice", pin="wrong")
    assert signed(client, secret, approval).status_code == 403
    approval.update(nonce="B" * 20, pin="human-alpha")
    assert signed(client, secret, approval).json()["state"] == "review_required"
    approval.update(nonce="D" * 20, identity="Bob", pin="human-bravo")
    assert signed(client, secret, approval).json()["state"] == "approved"
    monkeypatch.delenv("SENTINEL_DEVICE_SECRET")
    status = getstatus(client)
    assert not status["device_connected"] and status["state"] == "review_required" and not status["approvals"]


def test_wired_replay_is_persistent_and_failed_decisions_consume_nonce(wired):
    client, clock, path, secret = wired
    connect = event("connect", clock, "C" * 24)
    assert signed(client, secret, connect).status_code == 200
    assert signed(client, secret, connect).status_code == 409
    p = propose(client)
    bad = event("approve", clock, "X" * 24, session_id=p["session_id"], identity="Alice", pin="invalid")
    assert signed(client, secret, bad).status_code == 403
    bad["pin"] = "human-alpha"  # still a replay, although it has a new valid signature
    assert signed(client, secret, bad).status_code == 409
    app2 = FastAPI()
    app2.include_router(interlock.router)
    with TestClient(app2) as restarted:
        assert signed(restarted, secret, connect).status_code == 409
    with sqlite3.connect(path / "interlock.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM device_nonces").fetchone()[0] == 2
        audit = "\n".join(db.iterdump())
    assert secret not in audit and "human-alpha" not in audit and "invalid" not in audit.replace("invalid credentials", "")


def test_wired_expiry_timestamp_session_binding_and_lease(wired):
    client, clock, _, secret = wired
    assert signed(client, secret, event("connect", clock, "C" * 24, timestamp=int(clock[0]) - 61)).status_code == 403
    assert signed(client, secret, event("connect", clock, "D" * 24)).status_code == 200
    p = propose(client)
    wrong_session = event("approve", clock, "E" * 24, session_id="old-session", identity="Alice", pin="human-alpha")
    assert signed(client, secret, wrong_session).status_code == 409
    for identity, pin, nonce in (("Alice", "human-alpha", "F" * 24), ("Bob", "human-bravo", "G" * 24)):
        result = signed(client, secret, event("approve", clock, nonce, session_id=p["session_id"], identity=identity, pin=pin))
        assert result.status_code == 200
    assert getstatus(client)["state"] == "approved"
    clock[0] += 45
    s = getstatus(client)
    assert s["state"] == "review_required" and not s["device_connected"] and not s["approvals"]
    assert signed(client, secret, event("heartbeat", clock, "H" * 24)).status_code == 200
    assert getstatus(client)["state"] == "review_required" and not getstatus(client)["approvals"]
    clock[0] += 255
    assert getstatus(client)["state"] == "expired"
    assert signed(client, secret, event("approve", clock, "I" * 24, session_id=p["session_id"], identity="Alice", pin="human-alpha")).status_code == 409


def test_reject_unknown_events_and_require_configured_wired_secrets(wired, monkeypatch):
    client, clock, _, secret = wired
    assert signed(client, secret, event("launch", clock, "N" * 24)).status_code == 422
    assert signed(client, secret, event("heartbeat", clock, "O" * 24, identity="Alice")).status_code == 422
    monkeypatch.delenv("DEMO_PIN_ALICE")
    signed(client, secret, event("connect", clock, "P" * 24))
    p = propose(client)
    assert signed(client, secret, event("approve", clock, "Q" * 24, session_id=p["session_id"], identity="Alice", pin="1111")).status_code == 503
    assert getstatus(client)["state"] == "review_required"
    monkeypatch.setenv("SENTINEL_DEVICE_SECRET", "too-short")
    assert signed(client, secret, event("connect", clock, "R" * 24)).status_code == 503


def test_wired_rejection_is_authenticated_and_clears_approval(wired):
    client, clock, _, secret = wired
    signed(client, secret, event("connect", clock, "a" * 24))
    session = propose(client)["session_id"]
    signed(client, secret, event("approve", clock, "b" * 24, session_id=session, identity="Alice", pin="human-alpha"))
    result = signed(client, secret, event("reject", clock, "c" * 24, session_id=session, identity="Bob", pin="human-bravo"))
    assert result.status_code == 200 and result.json()["state"] == "rejected"
    assert result.json()["approvals"] == []
    assert any(item["event"] == "rejected" and "Bob" in item["detail"] for item in result.json()["audit"])


def test_wired_expiration_after_first_approval_prevents_second(wired):
    client, clock, _, secret = wired
    signed(client, secret, event("connect", clock, "d" * 24))
    session = propose(client)["session_id"]
    assert signed(client, secret, event("approve", clock, "e" * 24, session_id=session, identity="Alice", pin="human-alpha")).status_code == 200
    clock[0] += 300
    signed(client, secret, event("heartbeat", clock, "f" * 24))
    second = signed(client, secret, event("approve", clock, "g" * 24, session_id=session, identity="Bob", pin="human-bravo"))
    assert second.status_code == 409
    assert getstatus(client)["state"] == "expired" and not getstatus(client)["approvals"]
