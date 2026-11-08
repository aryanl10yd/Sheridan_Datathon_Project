# Sentinel Orbital

A defensive threat-intelligence and mission-assurance **simulation**. AI may suggest review, and agent tools do not provide approval access. The public demo identities do not prove a human made a decision. This project has no flight, satellite, launch, ground-station, or other infrastructure command interface.

## Current scope

No vulnerability datasets, IBM Granite credentials, or physical device were supplied with this project. The included demonstration data, timestamps, exploitation signals, mission inventory, operator identities and device are **fictional**. They are not real CVEs, current EPSS or KEV intelligence, actual human authentication, or evidence about a real organization. In the absence of configured Granite inference, the application clearly identifies deterministic demo responses; they are not Granite responses. A trained predictive model and valid evaluation results require suitable timestamped historical data and labels; the application does not invent them. The included historical evaluator is an offline demonstration, not a deployed prediction service. The included interlock is not a certified or production-ready safety or security control.

## Run locally

Requirements: Python 3.10+, Node.js 20+ and npm. From the project directory:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
npm ci
npm run build
cp .env.example .env
cp .env.interlock.example .env.interlock
./run.sh
```

Open `http://127.0.0.1:3000`. The launcher starts a local gateway, an intelligence service, and a separate interlock service. The gateway serves the built frontend and `/api` from the same origin. The services use ports 3000, 8000 and 8001; run one worker. To reload frontend edits, rebuild and restart the service. A container build is also provided: `docker build -t sentinel-orbital .` and `docker run -p 3000:3000 sentinel-orbital`.

## Configure Granite and datasets

Set the Granite endpoint, model identifier and credentials in `.env` or the process environment; keep interlock PINs and device secrets in the separate `.env.interlock` file; never commit real credentials. See `.env.example` and `docs/agents.md` for supported endpoint conventions. Agent inference is only labeled Granite when a configured service actually returns a valid response. Backend code uses allowlisted read-only tools; approval credentials are not included in agent prompts or agent tools. The services share a host by default and are not protected by OS-account isolation.

The named challenge datasets were not included. Put datasets in the configured dataset directory and follow `docs/data.md` for schema, ingestion, provenance, timestamp and evaluation requirements. Dataset schema and temporal availability must be verified before trusting any resulting analysis.

## Simulated interlock

Use the Flight Interlock page to propose a simulated operation, review it, and exercise two distinct demo identities, Alice and Bob. The example PINs are `1111` and `2222`, respectively, and can be configured in `.env.interlock` for local demonstration. They do not establish that two real humans participated. Disconnecting the simulated device causes a hold and does not grant approval. No hardware has been tested here. The gateway, interlock and agent services run as separate processes but normally share a user account and host; this is not OS-level isolation. In the demo, public PINs can be used by anyone or any program. Threat review is advisory and every proposal requires review regardless of its findings. The authorization audit does not retain or cryptographically bind the full agent investigation evidence. For the signed device protocol, state transitions and Raspberry Pi Zero wired-connection assumptions see `docs/interlock.md`.

## Tests and architecture

```sh
. .venv/bin/activate
python -m pytest -q
npm run build
python scripts/smoke_test.py
```

See `docs/architecture.md`, `docs/data.md`, `docs/agents.md`, `docs/interlock.md`, and `docs/cookbook-notes.md`. The cookbook notes identify the exact reviewed IBM repository commit, source files and adapted patterns. Local database files and container filesystems are not durable production storage. This is a prototype and must not be relied on for real-world safety decisions.
