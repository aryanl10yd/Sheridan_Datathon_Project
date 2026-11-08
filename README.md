# Vexcel

Vexcel is a focused scientific investigation and mission-control replay
for the May 10–11, 2024 geomagnetic storm. It uses the supplied NASA OMNI
five-minute CSV and does not synthesize missing observations.

<img width="1520" height="941" alt="Screen Shot 2026-11-08 at 4 34 35 AM" src="https://github.com/user-attachments/assets/0accee1f-0b90-43a8-9fc7-fc5e1a55776e" />

Menu open

<img width="1519" height="934" alt="Screen Shot 2026-11-08 at 4 34 25 AM" src="https://github.com/user-attachments/assets/21ebfd08-f027-41a6-a4fd-a654087e3214" />

Mission control

<img width="1519" height="934" alt="Screen Shot 2026-11-08 at 4 34 12 AM" src="https://github.com/user-attachments/assets/483df84e-3a93-4ce8-826c-0d563a439418" />


## Run the backend

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src uvicorn spaceweather.main:app --reload
```

The API reads `nasa_omni_solar_wind_storms_5min_2010-2026.csv` from the
repository root. Override it with `SPACEWEATHER_DATASET`. The analysis uses
three consecutive five-minute samples (15 minutes) below Bz -10 nT or SYM-H
-100 nT; missing samples break a sustained event.

## Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Configure a Vite proxy to `/api` to the backend for local development. The
service defaults to physical Raspberry Pi mode and reports the device as
disconnected until the authenticated Raspberry Pi Zero W v1.1 client connects.
Set `HARDWARE_TOKEN` consistently for the backend and device client. The
frontend keeps the four analysis sections client-side and exposes a shared
bottom Hardware Control Dock. The dock uses the authenticated
`/api/hardware/status` endpoint and the
`/api/hardware/self_test`, `/api/hardware/synchronize`, and
`/api/hardware/reset` commands; it never accesses GPIO directly.

## Connect the Raspberry Pi Zero W v1.1

The backend does not connect to the Pi from the browser. Run the device agent
on the Pi; it opens the authenticated WebSocket that the backend uses for
heartbeats, LED state, commands, and acknowledgements.

1. Make sure the Pi and the backend host can reach each other over the network.
2. On the backend host, set the shared token before starting FastAPI:

   ```bash
   export HARDWARE_TOKEN="use-a-long-random-token"
   export HARDWARE_MODE=physical
   cd backend
   PYTHONPATH=src uvicorn spaceweather.main:app --host 0.0.0.0 --port 8000
   ```

3. On the Pi, install the device dependencies and start the listener. Replace
   `BACKEND_HOST` with the backend host's LAN hostname or IP address:

   ```bash
   cd device
   python3 -m pip install -r requirements.txt
   python3 device_agent.py \
     --url ws://BACKEND_HOST:8000 \
     --token "$HARDWARE_TOKEN" \
     --listen
   ```

   For a physical Pi, do not pass `--simulate`. The agent reports the Pi
   hostname as its device ID and reads the model from
   `/proc/device-tree/model`; the dock shows those values after the first
   heartbeat. If the agent is stopped, the dock changes to disconnected.

## Historical analytics and mission control

The frontend includes a backend-downsampled 2010–2026 SYM-H timeline that
preserves observed extrema and highlights May 10–11, 2024; the existing
Bz/SYM-H investigation; and a pairwise-complete Pearson correlation heatmap
for solar-wind speed, dynamic pressure, IMF Bz GSM, and AE. Correlations are
associations and do not establish causation.

Mission Control provides backend-authoritative row-by-row replay with play,
pause, reset, step, seek, and 1x/2x/5x/10x playback. Status thresholds are
demonstration thresholds, not official NOAA classifications.

SAFE MODE CONFIRMATION records a UTC event ID and replay state for one of two
simulated responses. It never performs electrical switching or spacecraft
commands. Authorized events are sent to authenticated WebSocket hardware
clients, where the blue LED indicates authorization.

## Tests

```bash
PYTHONPATH=backend/src pytest -q backend/tests
cd frontend && npm test
cd frontend && npm run build
```
