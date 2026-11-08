# Simulated flight interlock

**Prototype only.** This subsystem never sends a flight, launch, spacecraft, ground-station, or infrastructure command. An `approved` status means only that a simulated workflow has two recorded demo approvals; it is not authority to control anything. There is no GPIO driver or real hardware safety circuit in this prototype.

## Demo and identity limitations

The default mode is `demo`. The connection is **simulated and initially connected**, even when there is no physical device. The `/device` toggle simulates a connection or failure; it does not verify hardware. The two local demo identities and default PINs are **Alice / 1111** and **Bob / 2222**. Override them with `DEMO_PIN_ALICE` and `DEMO_PIN_BOB`. Both must be nonempty and different. These public, low-strength PINs are **not identity assurance**: a person or program with the PIN can impersonate either identity. The system cannot establish that two actual people approved or distinguish an AI from a human. Never use these defaults to protect anything consequential.

**Agent isolation is a deployment responsibility, not a guarantee of this demo router.** Do not provide PINs, device keys, signed request bodies, or approval/rejection tools to any agent or model. Do not allow agent tools or retrieved content to invoke the approval API. The router exposes no credentials in status or audit and is independent of the agent code, but any process that can read its environment or access the endpoints and guess the public defaults can approve. The supplied `run.sh` launches the router, gateway and agent service as separate processes and removes interlock secrets from the agent process environment. They still normally share an OS account and filesystem, so this is not strong OS isolation; the gateway sees approval requests in transit. For a stronger demonstration boundary run a separate interlock process under a different OS account with separate secret delivery and restrictive network/file permissions, and give agents no access to its decision interface. Even then, this prototype is **not** a production authorization solution.

## API integration

The independent FastAPI `APIRouter` is `app.interlock.router`, already prefixed `/api/interlock`. To embed it in a FastAPI application:

```python
from app.interlock import router as interlock_router
app.include_router(interlock_router)
```

Do not prefix it a second time. The application launcher already runs it as a separate process. To run it independently from the project root, with FastAPI and Uvicorn installed:

```bash
python -c 'from fastapi import FastAPI; from app.interlock import router; import uvicorn; a=FastAPI(); a.include_router(router); uvicorn.run(a, host="127.0.0.1", port=8001)'
```

This server is local-only. Configuration is read from the process environment; restart the process after changing it. If rotating credentials, first disconnect/invalidate the current session. The demo endpoints are:

| Method/path | JSON body | Behavior |
|---|---|---|
| `GET /api/interlock/status` | — | Status snapshot; performs expiry and lease checks before returning. |
| `POST /api/interlock/propose` | `{"action":"Simulate a mission hold release"}` | Starts a new review session. An already pending review must first be rejected or expire. |
| `POST /api/interlock/approve` | `{"identity":"Alice","pin":"1111","session_id":"CURRENT_SESSION_ID","nonce":"FRESH_RANDOM_NONCE"}` | Demo-only approval; must be authenticated, connected, unexpired, session-bound and distinct. |
| `POST /api/interlock/reject` | `{"identity":"Bob","pin":"2222","session_id":"CURRENT_SESSION_ID","nonce":"FRESH_RANDOM_NONCE"}` | Demo-only authenticated, session-bound rejection; clears any approvals. |
| `POST /api/interlock/device` | `{"connected":false}` | Demo-only simulated disconnect/reconnect; the boolean is strict. |
| `POST /api/interlock/device/event` | Signed event, described below | Wired mode only; PIN decisions cannot use the direct demo endpoints. |

All successful calls return the same status object:

```json
{"operation":null,"state":"idle","approvals":[],"device_connected":true,
 "review_reason":null,"audit":[],"expires_at":null,"mode":"demo","session_id":null}
```

For a proposed operation, `approvals` contains `{ "identity": "Alice", "at": "...Z" }` entries, `audit` contains `{ "at", "event", "detail" }` objects, and `expires_at` is a UTC timestamp. `session_id` is a non-secret random identifier used to bind **both demo and wired** decisions to the current operation. The status response contains the latest 250 audit events in order; the SQLite table retains the full history until explicitly deleted. `review_reason` is a generic simulation-review explanation, **not** a claim that threat evidence was analyzed.

Every demo approval or rejection requires all four string fields: `identity`, `pin`, `session_id`, and `nonce`. Obtain the session ID from the proposal or latest status response and send it exactly; decisions require a current, unexpired `review_required` session. When there is no current session (`session_id` is initially `null`), a decision cannot succeed. A retained ID after approval, rejection, or expiry is not itself an active review. Generate a **new, unpredictable nonce for every attempt**, including retries, using `crypto.randomUUID()` in a browser (or another cryptographically secure generator). The nonce must be 16–128 ASCII characters matching `[A-Za-z0-9_-]`; UUID strings are valid. The server checks syntax and uniqueness, not whether the caller actually used a random generator. There is no identity/PIN-only compatibility path.

Demo nonces are recorded globally across both endpoints and all demo sessions in persistent SQLite, atomically with the decision. A parseable JSON object containing a syntactically valid nonce consumes it even when the request is denied, including missing or invalid other fields, bad PINs, no active session, and wrong session IDs. Once consumed it cannot be reused after changing any field, switching between approve/reject, starting a new session, or restarting the process. A malformed JSON body, or a missing/invalid nonce, has no usable nonce to consume. Wired events retain their separate signed-event nonce rules described below. This replay protection does not make the demo PINs or endpoint access secure: unauthenticated callers can consume demo nonces and fill storage.

Requests with a bad human PIN or device signature return `403`; invalid/duplicate/out-of-order transitions and replayed nonces return `409`; invalid bodies return `422`; unavailable storage or invalid configuration returns `503`. No error permits authorization. Do not paste real credentials into an operation description. Example using the public demo defaults only (these commands may be recorded in shell history and must never be used with actual secrets):

```bash
curl -s http://127.0.0.1:8001/api/interlock/status
PROPOSAL=$(curl -fsS -H 'Content-Type: application/json' -d '{"action":"Simulated hold release"}' http://127.0.0.1:8001/api/interlock/propose)
SESSION_ID=$(printf '%s' "$PROPOSAL" | python3 -c 'import json,sys; print(json.load(sys.stdin)["session_id"])')
curl -s -H 'Content-Type: application/json' -d "{\"identity\":\"Alice\",\"pin\":\"1111\",\"session_id\":\"$SESSION_ID\",\"nonce\":\"$(python3 -c 'import uuid; print(uuid.uuid4())')\"}" http://127.0.0.1:8001/api/interlock/approve
curl -s -H 'Content-Type: application/json' -d "{\"identity\":\"Bob\",\"pin\":\"2222\",\"session_id\":\"$SESSION_ID\",\"nonce\":\"$(python3 -c 'import uuid; print(uuid.uuid4())')\"}" http://127.0.0.1:8001/api/interlock/approve
curl -s -H 'Content-Type: application/json' -d '{"connected":false}' http://127.0.0.1:8001/api/interlock/device
```

The last request invalidates **both** approvals and returns the operation to review-required. Reconnecting does not restore either approval. While review is pending, a rejection uses the same session ID but its own fresh nonce:

```bash
curl -s -H 'Content-Type: application/json' -d "{\"identity\":\"Bob\",\"pin\":\"2222\",\"session_id\":\"$SESSION_ID\",\"nonce\":\"$(python3 -c 'import uuid; print(uuid.uuid4())')\"}" http://127.0.0.1:8001/api/interlock/reject
```

Tests: `python -m pytest -q tests/test_interlock.py` from the project root.

## State machine and storage

`idle` → `review_required` on proposal. With a connected device, the first authorized identity leaves it in `review_required`; a second *different* identity changes it to `approved`. An authenticated rejection from review clears the approvals and enters `rejected`. Expiration clears approvals and enters `expired`. A disconnect after one or both approvals clears them; an `approved` operation returns to `review_required` until the session itself expires. A proposal after `approved`, `rejected`, or `expired` starts a fresh operation and session; proposing while review is pending is denied. Invalid credentials, a duplicate identity, a disconnected device, a wrong session, a stale event, or a missing approval cannot produce `approved`.

Defaults and configuration:

| Environment variable | Default | Purpose |
|---|---|---|
| `SENTINEL_INTERLOCK_MODE` | `demo` | `demo` or `wired`; changing mode disconnects and invalidates approvals. |
| `DEMO_PIN_ALICE`, `DEMO_PIN_BOB` | `1111`, `2222` **in demo only** | Distinct PINs. In wired mode both must be explicitly set; no wired PIN defaults are supplied. These are still demo identities. |
| `SENTINEL_DEVICE_SECRET` | none | Wired HMAC key, UTF-8, at least 32 bytes; configure the same strong random secret on server and device, via a protected channel. |
| `SENTINEL_INTERLOCK_DB` | `<project>/data/interlock.sqlite3` | Persistent SQLite database, including replay nonces. Use a private, durable directory. |
| `SENTINEL_INTERLOCK_TTL_SECONDS` | `300` | Session lifetime, 1–86400 seconds; approval does not extend it. |
| `SENTINEL_INTERLOCK_DEVICE_LEASE_SECONDS` | `45` | Wired heartbeat lease, 1–3600 seconds. |
| `SENTINEL_INTERLOCK_CLOCK_SKEW_SECONDS` | `60` | Maximum signed timestamp skew, 1–600 seconds. |

SQLite transactions serialize state changes and nonce consumption; a new database file is created with mode `0600` where supported. Existing directory/file permissions, backups, disk encryption and OS access controls remain the operator's responsibility. Do not put a shared SQLite database on an unsuitable network filesystem. Audit entries avoid PINs, keys, signatures, operation text and raw event bodies, but are neither encrypted nor tamper-evident; database access can alter them. Separate demo and wired nonce tables retain consumed nonces, including those used by denied decisions, so provision and monitor storage. Do not reset or restore the database to an older snapshot while relying on replay protection: doing so can lose nonce history. Storage failure produces `503`, not an approval. Removing the wired secret invalidates the device lease on the next status or action.

Expiry and lease checks happen transactionally on **each request**, including status reads and device events; there is no background watchdog. Clients must poll status and must not cache a past `approved` result. Loss of heartbeat is detected on the next request, so dashboard state can appear stale without polling. Both mechanisms rely on an accurate system clock; severe clock tampering or unreliable storage is outside the prototype's protection.

## Wired-device protocol and Pi Zero stub

The original Raspberry Pi Zero has a micro-USB OTG data port, a separate micro-USB power input and a 40-pin header; it has no built-in wireless networking. See the [official Raspberry Pi Zero specifications](https://www.raspberrypi.com/products/raspberry-pi-zero/). Use a deliberately configured **wired** IP connection, such as an appropriate USB Ethernet/gadget link or a wired USB Ethernet adapter, and power the Pi suitably. Do not assume Wi-Fi. The standard-library-only `device/device.py` client is a terminal-driven stub; it does not interface with GPIO, a flight computer, or any external control system. A future physical console could indicate connection/review/approval states and gather deliberate button input, but must not be represented as independently secure without a separate engineering and safety review.

On the laptop run the interlock in `wired` mode on loopback. Set `SENTINEL_INTERLOCK_MODE=wired`, distinct `DEMO_PIN_ALICE` and `DEMO_PIN_BOB`, and a unique strong `SENTINEL_DEVICE_SECRET` in **only that process**. Set the same device secret in the Pi device process, not the agent process. Deliver secrets privately; environment variables are visible to sufficiently privileged local processes and are not a production secret store. The Pi does not need either human PIN in its environment: the stub prompts interactively with echo disabled when a decision is submitted.

The device stub refuses cleartext HTTP except on localhost. For a wired SSH link, run an authenticated SSH local forward on the Pi (replace `USER@LAPTOP` with the reachable wired host; verify SSH host keys):

```bash
ssh -N -L 8001:127.0.0.1:8001 USER@LAPTOP
# In another Pi terminal, provision SENTINEL_DEVICE_SECRET privately, then:
python3 device/device.py --url http://127.0.0.1:8001 watch
```

This establishes a signed connection and sends heartbeats every 15 seconds by default. For decisions, propose an operation from the UI, obtain its `session_id` from status, and in another protected terminal run the following for each human; each PIN is entered at the interactive prompt:

```bash
python3 device/device.py --url http://127.0.0.1:8001 approve --session-id SESSION_ID --identity Alice
python3 device/device.py --url http://127.0.0.1:8001 approve --session-id SESSION_ID --identity Bob
# Or: python3 device/device.py --url http://127.0.0.1:8001 reject --session-id SESSION_ID --identity Alice
```

Use Python 3.10 or newer. A device process may alternatively connect to an HTTPS origin with correctly verified TLS certificates. The sample client supports `connect`, `heartbeat`, `disconnect`, `approve`, `reject` and `watch`. Ctrl-C in `watch` attempts a signed disconnect; if the connection is already broken, the lease expires instead. Do not set the heartbeat interval equal to or greater than the server lease. Connectivity does not by itself authorize anything.

### Exact wire format

`POST /api/interlock/device/event` accepts a JSON UTF-8 body, maximum 4096 bytes, with these only allowed events:

```json
{"event":"heartbeat","timestamp":1800000000,"nonce":"a-unique-random-nonce-at-least-16-characters"}
{"event":"approve","timestamp":1800000000,"nonce":"another-unique-random-nonce-value","session_id":"CURRENT_SESSION_ID","identity":"Alice","pin":"HUMAN_PIN"}
```

`connect`, `heartbeat` and `disconnect` contain only `event`, `timestamp` and `nonce`; `approve` and `reject` also require `session_id`, `identity` and `pin`. `timestamp` is integer Unix time in seconds; nonce is a fresh, unpredictable 16–128-character ASCII `[A-Za-z0-9_-]` value for **every** attempt. The required header `X-Interlock-Signature` is lowercase hexadecimal `HMAC-SHA256(secret_utf8, b"sentinel-interlock-v1\n" + exact_raw_body_bytes)`, where `\n` denotes one newline byte. Sign the bytes actually sent, not a parsed/reserialized object. Compare is constant-time. Well-formed, in-window, correctly signed nonces are persisted in the same transaction as the decision and cannot be reused, even after process restart or if the decision was denied. Timestamps outside the allowed window are denied; decisions with an incorrect or expired operation session are denied. The wired connection lease is based on authenticated connect/heartbeat events, not on the demo toggle.

HMAC provides integrity/authentication **not confidentiality**: the PIN appears in the signed body. Protect the entire connection with verified TLS or an authenticated SSH tunnel and do not log request bodies. Protect secrets, clocks, endpoint access and the host; the client cannot independently detect a compromised server. The stub does not implement hardware-backed keys, secure boot, signed firmware, challenge/response identity, anti-brute-force controls, mutual TLS, independent physical attestation, tamper resistance, highly available fail-safe circuitry, or safety certification. It must not be deployed to an operational flight or safety-critical environment.
