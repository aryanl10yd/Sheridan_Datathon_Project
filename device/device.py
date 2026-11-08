#!/usr/bin/env python3
"""Wired interlock *simulation* client. It has no flight-command functionality.

Use a protected tunnel or HTTPS; never pass PINs or the shared key on the command line.
See docs/interlock.md. No GPIO or wireless hardware is required.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PREFIX = b"sentinel-interlock-v1\n"


def checked_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("URL must be an origin without credentials, path, query or fragment")
    if not (parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost", "::1"))):
        raise ValueError("Use HTTPS or a localhost HTTP tunnel; cleartext network HTTP is refused")
    return value.rstrip("/")


def request_event(base: str, key: bytes, event: str, session_id: str | None = None,
                  identity: str | None = None, pin: str | None = None) -> dict:
    payload = {"event": event, "timestamp": int(time.time()), "nonce": secrets.token_urlsafe(24)}
    if session_id is not None:
        payload["session_id"] = session_id
    if identity is not None:
        payload["identity"] = identity
    if pin is not None:
        payload["pin"] = pin
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    signature = hmac.new(key, PREFIX + raw, hashlib.sha256).hexdigest()
    req = urllib.request.Request(base + "/api/interlock/device/event", data=raw,
                                 headers={"Content-Type": "application/json", "X-Interlock-Signature": signature},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


def show_status(status: dict) -> None:
    print(json.dumps({k: status.get(k) for k in ("state", "device_connected", "expires_at", "session_id", "mode")}), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulated wired Sentinel interlock. NO FLIGHT COMMANDS.")
    parser.add_argument("event", choices=("connect", "heartbeat", "disconnect", "approve", "reject", "watch"))
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="HTTPS origin, or localhost HTTP over a protected tunnel")
    parser.add_argument("--session-id", help="Current session ID from /api/interlock/status; required for decisions")
    parser.add_argument("--identity", choices=("Alice", "Bob"), help="Required for decisions")
    parser.add_argument("--interval", type=int, default=15, help="Heartbeat seconds for watch (must be less than server lease)")
    args = parser.parse_args()
    try:
        base = checked_url(args.url)
        key = os.environ.get("SENTINEL_DEVICE_SECRET", "").encode("utf-8")
        if len(key) < 32:
            raise ValueError("SENTINEL_DEVICE_SECRET must be set to at least 32 bytes")
        if args.event in ("approve", "reject"):
            if not args.session_id or not args.identity:
                raise ValueError("--session-id and --identity are required for decisions")
            pin = getpass.getpass("Human demo PIN (not echoed): ")
            result = request_event(base, key, args.event, args.session_id, args.identity, pin)
            show_status(result)
        elif args.event == "watch":
            if args.interval < 1:
                raise ValueError("Heartbeat interval must be positive")
            show_status(request_event(base, key, "connect"))
            try:
                while True:
                    time.sleep(args.interval)
                    show_status(request_event(base, key, "heartbeat"))
            except KeyboardInterrupt:
                try:
                    show_status(request_event(base, key, "disconnect"))
                except (urllib.error.URLError, TimeoutError, OSError):
                    print("Disconnected locally; server lease will expire.", file=sys.stderr)
        else:
            show_status(request_event(base, key, args.event))
        return 0
    except (ValueError, urllib.error.URLError, TimeoutError, OSError) as exc:
        # Do not print request bodies, credentials, keys, or server response bodies.
        if isinstance(exc, urllib.error.HTTPError):
            print(f"Interlock request denied (HTTP {exc.code}); no operation was authorized.", file=sys.stderr)
        else:
            print("Interlock request failed or configuration is invalid; no operation was authorized.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
