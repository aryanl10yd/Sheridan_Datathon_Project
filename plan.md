# Sentinel Orbital implementation plan

Build a runnable defensive threat-intelligence demonstration, never an operational flight control system. The only supplied input is the project brief: the listed CSVs, IBM credentials, and hardware were not supplied. Provide openly labeled fictional records and a deterministic demonstration agent mode, and make real ingestion and Granite inference configurable. Never fabricate model evaluations or live evidence.

## Architecture

A FastAPI application serves a Vite/React/TypeScript SPA and relative `/api` endpoints. `app/data.py`, `app/analytics.py` and `app/demo_data.py` own DuckDB ingestion, lookup, transparent momentum and leakage-aware model readiness/evaluation. A future data import remains lazy/query based, with quality reports. `app/agents.py` provides isolated role prompts, allow-listed read-only tools, routing and concurrent investigations, validated structured outputs, provenance, bounded inference calls, and independent verification; an OpenAI-compatible Granite endpoint and watsonx configuration are environment-based. `app/interlock.py` is a separate authorization state machine and device protocol, with no agent access to approval credentials; `device/` provides a lightweight wired-device simulator/prototype. `app/main.py` integrates bounded APIs and serves the SPA. Tests cover ingest, agent routing, provenance, ambiguity, and fail-closed authorization. Documentation records dataset and security limitations and IBM cookbook adaptations.

## Design

User-specified visual direction: restrained aerospace operations; deep navy and charcoal, cool cyan and electric blue, high-contrast status colors; professional, not science fiction. Use a fixed operational sidebar, a spacious left-aligned command workspace, compact evidence cards, fine-line borders and a restrained orbital mark. Use a clear sans-serif for interface hierarchy and monospace for identifiers, timestamps and instrumentation. Status chips identify simulated content and availability without overstating real-world intelligence. Preserve legibility and responsive layouts; motion is limited to subtle activity indicators.

The seven interfaces are Command Center, Threat Intelligence Explorer, Agent Operations, Exploitation Momentum, Mission Assurance, Flight Interlock and Evidence Reports. All displayed records and actions come from backend APIs, with explicit empty/error states and working navigation and controls.
