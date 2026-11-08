"""Sentinel Orbital simulated interlock; no command or flight-control capability.

This is a demonstration, not a security-certified identity or safety system.
See docs/interlock.md for the trust boundary and wire protocol.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr, ValidationError

router = APIRouter(prefix="/api/interlock", tags=["simulated interlock"])
_PREFIX = b"sentinel-interlock-v1\n"
_NONCE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_SIG = re.compile(r"^[0-9a-f]{64}$")
_REASON = "Simulated operation requires review and two distinct human approvals."


class Proposal(BaseModel):
    action: str = Field(min_length=1, max_length=500)


class HumanDecision(BaseModel):
    identity: StrictStr = Field(min_length=1, max_length=100)
    pin: StrictStr = Field(min_length=1, max_length=128, repr=False)
    session_id: StrictStr = Field(min_length=1, max_length=128)
    nonce: StrictStr = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]{16,128}$")


_HUMAN_DECISION_SCHEMA = (HumanDecision.model_json_schema() if hasattr(HumanDecision, "model_json_schema")
                          else HumanDecision.schema())


class DemoDevice(BaseModel):
    connected: StrictBool


class DeviceEvent(BaseModel):
    event: Literal["connect", "heartbeat", "disconnect", "approve", "reject"]
    timestamp: StrictInt
    nonce: str = Field(min_length=16, max_length=128)
    session_id: Optional[str] = Field(default=None, max_length=128)
    identity: Optional[str] = Field(default=None, max_length=100)
    pin: Optional[str] = Field(default=None, max_length=128, repr=False)

    class Config:
        extra = "forbid"


@dataclass(frozen=True)
class Settings:
    mode: str
    path: str
    ttl: int
    lease: int
    clock_skew: int


class Denied(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail


def _settings() -> Settings:
    mode = os.getenv("SENTINEL_INTERLOCK_MODE", "demo").lower()
    try:
        ttl = int(os.getenv("SENTINEL_INTERLOCK_TTL_SECONDS", "300"))
        lease = int(os.getenv("SENTINEL_INTERLOCK_DEVICE_LEASE_SECONDS", "45"))
        skew = int(os.getenv("SENTINEL_INTERLOCK_CLOCK_SKEW_SECONDS", "60"))
    except ValueError:
        raise HTTPException(503, "Invalid interlock configuration") from None
    if mode not in ("demo", "wired") or not (1 <= ttl <= 86400 and 1 <= lease <= 3600 and 1 <= skew <= 600):
        raise HTTPException(503, "Invalid interlock configuration")
    default = str(Path(__file__).resolve().parent.parent / "data" / "interlock.sqlite3")
    path = os.getenv("SENTINEL_INTERLOCK_DB", default)
    if not path or path == ":memory:":
        raise HTTPException(503, "Interlock requires a persistent database path")
    return Settings(mode, path, ttl, lease, skew)


def _utc(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _audit(db: sqlite3.Connection, now: float, event: str, detail: str) -> None:
    # Never insert request bodies, PINs, signatures, device keys or operation text.
    db.execute("INSERT INTO audit(at,event,detail) VALUES (?,?,?)", (_utc(now), event, detail))


def _open(settings: Settings) -> sqlite3.Connection:
    path = Path(settings.path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(fd)
    db = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("PRAGMA synchronous=FULL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS interlock_state (
          id INTEGER PRIMARY KEY CHECK(id=1), operation TEXT, state TEXT NOT NULL,
          review_reason TEXT, expires_at REAL, session_id TEXT,
          device_connected INTEGER NOT NULL, device_last_seen REAL, mode TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS approvals (identity TEXT PRIMARY KEY, at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, event TEXT NOT NULL, detail TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS device_nonces (nonce TEXT PRIMARY KEY, received_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS demo_nonces (nonce TEXT PRIMARY KEY, received_at TEXT NOT NULL);
    """)
    return db


def _state(db: sqlite3.Connection) -> sqlite3.Row:
    row = db.execute("SELECT * FROM interlock_state WHERE id=1").fetchone()
    if row is None:
        raise RuntimeError("interlock state missing")
    return row


def _invalidate_for_disconnect(db: sqlite3.Connection, now: float, why: str) -> None:
    row = _state(db)
    approvals = db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]
    db.execute("UPDATE interlock_state SET device_connected=0, device_last_seen=NULL WHERE id=1")
    if approvals or row["state"] == "approved":
        db.execute("DELETE FROM approvals")
        if row["state"] == "approved":
            db.execute("UPDATE interlock_state SET state='review_required' WHERE id=1")
        _audit(db, now, "approvals_invalidated", "Connection lost; all approvals cleared.")
    if row["device_connected"]:
        _audit(db, now, "device_disconnected", why)


def _refresh(db: sqlite3.Connection, settings: Settings, now: float) -> None:
    row = db.execute("SELECT * FROM interlock_state WHERE id=1").fetchone()
    if row is None:
        db.execute("INSERT INTO interlock_state(id,state,device_connected,mode) VALUES (1,'idle',?,?)", (int(settings.mode == "demo"), settings.mode))
        _audit(db, now, "initialized", "Simulated interlock initialized; no operation is authorized.")
        row = _state(db)
    if row["mode"] != settings.mode:
        _invalidate_for_disconnect(db, now, "Operating mode changed.")
        db.execute("UPDATE interlock_state SET mode=? WHERE id=1", (settings.mode,))
        _audit(db, now, "mode_changed", "Operating mode changed; device must reconnect.")
        row = _state(db)
    if row["state"] in ("review_required", "approved") and (row["expires_at"] is None or now >= row["expires_at"]):
        db.execute("DELETE FROM approvals")
        db.execute("UPDATE interlock_state SET state='expired' WHERE id=1")
        _audit(db, now, "session_expired", "Session expired; all approvals cleared.")
        row = _state(db)
    try:
        _credentials(settings)
    except Denied:
        count = db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]
        if count or row["state"] == "approved":
            db.execute("DELETE FROM approvals")
            if row["state"] == "approved":
                db.execute("UPDATE interlock_state SET state='review_required' WHERE id=1")
            _audit(db, now, "approvals_invalidated", "Human credential configuration invalid; approvals cleared.")
            row = _state(db)
    if settings.mode == "wired" and row["device_connected"] and (
        row["device_last_seen"] is None
        or now - row["device_last_seen"] >= settings.lease
        or row["device_last_seen"] > now + settings.clock_skew
        or len(os.getenv("SENTINEL_DEVICE_SECRET", "").encode("utf-8")) < 32
    ):
        _invalidate_for_disconnect(db, now, "Authenticated device lease or configuration is invalid.")


def _status(db: sqlite3.Connection) -> dict:
    row = _state(db)
    audit = db.execute("SELECT at,event,detail FROM (SELECT id,at,event,detail FROM audit ORDER BY id DESC LIMIT 250) ORDER BY id").fetchall()
    approvals = db.execute("SELECT identity,at FROM approvals ORDER BY at,identity").fetchall()
    return {
        "operation": row["operation"],
        "state": row["state"],
        "approvals": [dict(item) for item in approvals],
        "device_connected": bool(row["device_connected"]),
        "review_reason": row["review_reason"],
        "audit": [dict(item) for item in audit],
        "expires_at": _utc(row["expires_at"]) if row["expires_at"] is not None else None,
        "mode": row["mode"],
        # Non-secret, random operation identifier, required to bind all decisions.
        "session_id": row["session_id"],
    }


def _transaction(operation):
    settings = _settings()
    db = None
    try:
        db = _open(settings)
        db.execute("BEGIN IMMEDIATE")
        now = time.time()
        _refresh(db, settings, now)
        try:
            result = operation(db, settings, now)
        except Denied as error:
            # Commit expiry, invalidation, audit, and consumed nonces even on denial.
            db.commit()
            raise HTTPException(error.status, error.detail) from None
        db.commit()
        return result
    except HTTPException:
        raise
    except (sqlite3.Error, OSError, RuntimeError):
        if db is not None:
            db.rollback()
        raise HTTPException(503, "Interlock storage unavailable; authorization denied") from None
    finally:
        if db is not None:
            db.close()


def _credentials(settings: Settings):
    names = ("Alice", "Bob")
    pins = (os.getenv("DEMO_PIN_ALICE"), os.getenv("DEMO_PIN_BOB"))
    if settings.mode == "demo":
        pins = (pins[0] if pins[0] is not None else "1111", pins[1] if pins[1] is not None else "2222")
    if (not all(names) or any(len(n) > 100 for n in names) or names[0] == names[1]
        or not all(pins) or any(len(p or "") > 128 for p in pins) or pins[0] == pins[1]):
        raise Denied(503, "Interlock identity configuration invalid; authorization denied")
    return tuple(zip(names, (pins[0] or "", pins[1] or "")))


def _authenticate(db: sqlite3.Connection, settings: Settings, now: float, identity: str, pin: str) -> str:
    matched = None
    try:
        credentials = _credentials(settings)
    except Denied:
        _audit(db, now, "authentication_denied", "Human credential configuration is invalid.")
        raise
    for name, candidate in credentials:
        name_ok = hmac.compare_digest(identity.encode("utf-8"), name.encode("utf-8"))
        pin_ok = hmac.compare_digest(pin.encode("utf-8"), candidate.encode("utf-8"))
        if name_ok and pin_ok:
            matched = name
    if matched is None:
        _audit(db, now, "authentication_failed", "Human decision denied: invalid credentials.")
        raise Denied(403, "Invalid human credentials")
    return matched


def _decision(db: sqlite3.Connection, settings: Settings, now: float, event: str, identity: str, pin: str, session_id: str) -> dict:
    name = _authenticate(db, settings, now, identity, pin)
    row = _state(db)
    if not row["session_id"] or not hmac.compare_digest(session_id.encode(), row["session_id"].encode()):
        _audit(db, now, "decision_denied", "Decision did not match the active session.")
        raise Denied(409, "Decision does not match the active session")
    if row["state"] != "review_required":
        _audit(db, now, "decision_denied", "No active operation awaiting review.")
        raise Denied(409, "No active operation awaiting review")
    if event == "reject":
        db.execute("DELETE FROM approvals")
        db.execute("UPDATE interlock_state SET state='rejected' WHERE id=1")
        _audit(db, now, "rejected", f"{name} rejected the simulated operation; approvals cleared.")
        return _status(db)
    if not row["device_connected"]:
        _audit(db, now, "approval_denied", "Device is disconnected or unverified.")
        raise Denied(409, "Device is disconnected or unverified")
    if db.execute("SELECT 1 FROM approvals WHERE identity=?", (name,)).fetchone():
        _audit(db, now, "approval_denied", "Duplicate identity cannot provide a second approval.")
        raise Denied(409, "A distinct identity is required")
    db.execute("INSERT INTO approvals(identity,at) VALUES (?,?)", (name, _utc(now)))
    count = db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]
    _audit(db, now, "approval_recorded", f"{name} approval recorded ({count} of 2).")
    if count == 2:
        db.execute("UPDATE interlock_state SET state='approved' WHERE id=1")
        _audit(db, now, "approved", "Two distinct approvals recorded for this simulated operation.")
    return _status(db)


@router.get("/status")
def status():
    return _transaction(lambda db, settings, now: _status(db))


@router.post("/propose")
def propose(body: Proposal):
    action = body.action.strip()
    if not action:
        raise HTTPException(422, "Action must not be blank")
    def apply(db, settings, now):
        if _state(db)["state"] == "review_required":
            _audit(db, now, "proposal_denied", "An operation is already awaiting review.")
            raise Denied(409, "An operation is already awaiting review")
        db.execute("DELETE FROM approvals")
        db.execute("UPDATE interlock_state SET operation=?,state='review_required',review_reason=?,expires_at=?,session_id=? WHERE id=1", (action, _REASON, now + settings.ttl, secrets.token_urlsafe(24)))
        _audit(db, now, "proposed", "A simulated operation was proposed for human review.")
        return _status(db)
    return _transaction(apply)


def _demo_decision(body: Any, event: str):
    def apply(db, settings, now):
        if settings.mode != "demo":
            _audit(db, now, "approval_denied" if event == "approve" else "decision_denied",
                   f"Direct {event} disabled in wired mode.")
            raise Denied(403, "Use the authenticated device in wired mode")

        # Consume any syntactically usable nonce before validating the other fields.
        # This includes bad credentials, missing fields, and absent/wrong sessions.
        nonce = body.get("nonce") if isinstance(body, dict) else None
        if not isinstance(nonce, str) or not _NONCE.fullmatch(nonce):
            raise Denied(422, "Decision requires a valid nonce")
        try:
            db.execute("INSERT INTO demo_nonces(nonce,received_at) VALUES (?,?)", (nonce, _utc(now)))
        except sqlite3.IntegrityError:
            _audit(db, now, "demo_replay_denied", "Demo decision nonce was already used.")
            raise Denied(409, "Demo decision replay denied")
        try:
            decision = HumanDecision(**body)
            # JSON can contain lone surrogates, which cannot be UTF-8 encoded by
            # the credential/session comparisons. Deny without undoing the nonce.
            for value in (decision.identity, decision.pin, decision.session_id):
                value.encode("utf-8")
        except (TypeError, ValidationError, UnicodeError):
            raise Denied(422, "Decision requires identity, PIN, session_id and nonce") from None
        return _decision(db, settings, now, event, decision.identity, decision.pin, decision.session_id)
    return _transaction(apply)


@router.post("/approve")
def approve(body: Any = Body(..., json_schema_extra=_HUMAN_DECISION_SCHEMA)):
    return _demo_decision(body, "approve")


@router.post("/reject")
def reject(body: Any = Body(..., json_schema_extra=_HUMAN_DECISION_SCHEMA)):
    return _demo_decision(body, "reject")


@router.post("/device")
def demo_device(body: DemoDevice):
    def apply(db, settings, now):
        if settings.mode != "demo":
            _audit(db, now, "device_change_denied", "Simulated connectivity toggle disabled in wired mode.")
            raise Denied(403, "Simulated toggle is available in demo mode only")
        if body.connected and not _state(db)["device_connected"]:
            db.execute("UPDATE interlock_state SET device_connected=1 WHERE id=1")
            _audit(db, now, "device_connected", "Simulated device connected; no hardware is verified.")
        elif not body.connected:
            _invalidate_for_disconnect(db, now, "Simulated device disconnected.")
        return _status(db)
    return _transaction(apply)


@router.post("/device/event")
async def device_event(request: Request):
    settings = _settings()
    if settings.mode != "wired":
        raise HTTPException(403, "Authenticated device events require wired mode")
    key = os.getenv("SENTINEL_DEVICE_SECRET", "").encode("utf-8")
    if len(key) < 32:
        raise HTTPException(503, "Device key is not configured; device remains unverified")
    raw = await request.body()
    if len(raw) > 4096:
        raise HTTPException(413, "Device event too large")
    signature = request.headers.get("X-Interlock-Signature", "")
    expected = hmac.new(key, _PREFIX + raw, hashlib.sha256).hexdigest()
    if not _SIG.fullmatch(signature) or not hmac.compare_digest(signature, expected):
        def failed(db, current, now):
            _audit(db, now, "device_authentication_failed", "Device event signature was invalid.")
            raise Denied(403, "Invalid device authentication")
        return _transaction(failed)
    try:
        payload = json.loads(raw)
        event = DeviceEvent(**payload)
    except (ValueError, TypeError):
        raise HTTPException(422, "Invalid device event") from None
    if not _NONCE.fullmatch(event.nonce):
        raise HTTPException(422, "Invalid device nonce")
    if event.event in ("approve", "reject"):
        if not event.session_id or not event.identity or not event.pin:
            raise HTTPException(422, "Device decision requires session, identity and PIN")
    elif event.session_id is not None or event.identity is not None or event.pin is not None:
        raise HTTPException(422, "Unexpected fields in device event")
    def apply(db, current, now):
        if current.mode != "wired":
            raise Denied(403, "Authenticated device events require wired mode")
        if abs(now - event.timestamp) > current.clock_skew:
            _audit(db, now, "device_event_denied", "Device event timestamp is outside the allowed window.")
            raise Denied(403, "Stale or future device event")
        try:
            db.execute("INSERT INTO device_nonces(nonce,received_at) VALUES (?,?)", (event.nonce, _utc(now)))
        except sqlite3.IntegrityError:
            _audit(db, now, "device_replay_denied", "Device event nonce was already used.")
            raise Denied(409, "Device event replay denied")
        if event.event in ("connect", "heartbeat"):
            was_connected = bool(_state(db)["device_connected"])
            db.execute("UPDATE interlock_state SET device_connected=1,device_last_seen=? WHERE id=1", (now,))
            if not was_connected:
                _audit(db, now, "device_connected", "Authenticated device connection established.")
            # Ordinary heartbeats are intentionally not added to the audit to avoid flooding it.
            return _status(db)
        if event.event == "disconnect":
            _invalidate_for_disconnect(db, now, "Authenticated device disconnected.")
            return _status(db)
        return _decision(db, current, now, event.event, event.identity or "", event.pin or "", event.session_id or "")
    return _transaction(apply)
