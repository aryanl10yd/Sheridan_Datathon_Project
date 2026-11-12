# Sheridan_Datathon_Project

Sheridan Datathon Project, made by Aryan, Eric, Terry, Rita.

### Vexcel — Space Weather Analytics & Mission Control

Vexcel is a focused scientific investigation and mission-control replay platform for the May 10–11, 2024 geomagnetic storm. It uses the supplied NASA OMNI five-minute CSV and does not synthesize missing observations.

🏆 Winner — Hardware Track, Sheridan Datathon 2026

## Scientific Overview

Geomagnetic storms occur when disturbances in the solar wind interact with Earth's magnetosphere. These interactions can produce significant disturbances in Earth's magnetic field, with potential implications for satellite operations, radio communications, navigation systems, and electrical power infrastructure.

The May 10–11, 2024 geomagnetic storm, commonly known as the Gannon Superstorm, provides the central investigation for Vexcel.

Vexcel investigates the relationship between upstream solar-wind conditions and geomagnetic responses through historical NASA OMNI observations. Particular attention is given to:

- **IMF Bz GSM:** The north-south component of the interplanetary magnetic field. Strongly negative Bz conditions can facilitate magnetic reconnection and coupling between the solar wind and Earth's magnetosphere.
- **Solar-wind speed:** The velocity of the incoming solar-wind plasma.
- **Dynamic pressure:** The pressure exerted by the solar wind.
- **AE index:** An indicator of auroral electrojet activity.
- **SYM-H:** A high-resolution geomagnetic index used to investigate disturbances in Earth's magnetic field.

## Screenshots

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

The API reads `nasa_omni_solar_wind_storms_5min_2010-2026.csv` from the repository root. Override it with `SPACEWEATHER_DATASET`. The analysis uses three consecutive five-minute samples (15 minutes) below Bz -10 nT or SYM-H -100 nT; missing samples break a sustained event.

## Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Configure a Vite proxy to `/api` to the backend for local development. The service defaults to physical Raspberry Pi mode and reports the device as disconnected until the authenticated Raspberry Pi Zero W v1.1 client connects. Set `HARDWARE_TOKEN` consistently for the backend and device client. The frontend keeps the four analysis sections client-side and exposes a shared bottom Hardware Control Dock. The dock uses the authenticated `/api/hardware/status` endpoint and the `/api/hardware/self_test`, `/api/hardware/synchronize`, and `/api/hardware/reset` commands; it never accesses GPIO directly.

## Connect the Raspberry Pi Zero W v1.1

The backend does not connect to the Pi from the browser. Run the device agent on the Pi; it opens the authenticated WebSocket that the backend uses for heartbeats, LED state, commands, and acknowledgements.

1. Make sure the Pi and the backend host can reach each other over the network.
2. On the backend host, set the shared token before starting FastAPI:

   ```bash
   export HARDWARE_TOKEN="use-a-long-random-token"
   export HARDWARE_MODE=physical
   cd backend
   PYTHONPATH=src uvicorn spaceweather.main:app --host 0.0.0.0 --port 8000
   ```

3. On the Pi, install the device dependencies and start the listener. Replace `BACKEND_HOST` with the backend host's LAN hostname or IP address:

   ```bash
   cd device
   python3 -m pip install -r requirements.txt
   python3 device_agent.py \
     --url ws://BACKEND_HOST:8000 \
     --token "$HARDWARE_TOKEN" \
     --listen
   ```

   For a physical Pi, do not pass `--simulate`. The agent reports the Pi hostname as its device ID and reads the model from `/proc/device-tree/model`; the dock shows those values after the first heartbeat. If the agent is stopped, the dock changes to disconnected.

## Historical analytics and mission control

The frontend includes a backend-downsampled 2010–2026 SYM-H timeline that preserves observed extrema and highlights May 10–11, 2024; the existing Bz/SYM-H investigation; and a pairwise-complete Pearson correlation heatmap for solar-wind speed, dynamic pressure, IMF Bz GSM, and AE.

During the May 10–11, 2024 event, SYM-H reached approximately -497 nT, highlighting the intensity of the geomagnetic disturbance. Vexcel provides a dedicated 48-hour investigation comparing IMF Bz and SYM-H observations throughout the event.

Mission Control provides backend-authoritative row-by-row replay with play, pause, reset, step, seek, and 1x/2x/5x/10x playback. Status thresholds are demonstration thresholds, not official NOAA classifications.

SAFE MODE CONFIRMATION records a UTC event ID and replay state for one of two simulated responses. It never performs electrical switching or spacecraft commands. Authorized events are sent to authenticated WebSocket hardware clients, where the blue LED indicates authorization.

## Data Source and Methodology

Vexcel uses the supplied NASA OMNI five-minute dataset:

`nasa_omni_solar_wind_storms_5min_2010-2026.csv`

The dataset contains historical solar-wind, interplanetary magnetic field, and geomagnetic measurements spanning 2010–2026.

Selected measurements used throughout the platform include:

| Parameter | Unit | Description |
|---|---|---|
| IMF Bz GSM | nT | North-south interplanetary magnetic field component |
| Solar-wind speed | km/s | Solar-wind velocity |
| Dynamic pressure | nPa | Solar-wind dynamic pressure |
| AE | nT | Auroral electrojet activity |
| SYM-H | nT | High-resolution geomagnetic disturbance index |

Vexcel preserves the original observations rather than synthesizing or interpolating missing measurements.

Sustained-event detection requires three consecutive five-minute observations (15 minutes) below either Bz -10 nT or SYM-H -100 nT. Missing observations break the consecutive-sample requirement.

The correlation heatmap uses pairwise-complete Pearson correlation, evaluating linear associations between available observations while accounting for missing values. Correlation does not establish causation.

## Tests

```bash
PYTHONPATH=backend/src pytest -q backend/tests
cd frontend && npm test
cd frontend && npm run build
```
