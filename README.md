# Sheridan_Datathon_Project

Sheridan Datathon Project, made by Aryan, Eric, Terry, Rita.

### Vexcel — Space Weather Analytics & Mission Control

## Overview

Vexcel is a focused scientific investigation and mission-control replay platform for the May 10–11, 2024 geomagnetic storm. It uses the supplied NASA OMNI five-minute dataset to investigate solar-wind conditions, geomagnetic disturbances, and their relationship during one of the strongest geomagnetic storms in recent history.

Geomagnetic storms occur when disturbances in the solar wind interact with Earth's magnetic field. These interactions can affect satellite operations, radio communications, navigation systems, and electrical power infrastructure. Understanding how solar-wind conditions evolve and how Earth's magnetic field responds is important for improving space-weather awareness.

Vexcel aims to make these complex interactions easier to investigate through historical data analysis, interactive visualizations, and mission-control telemetry replay.

Rather than generating synthetic observations or interpolating missing measurements, Vexcel works directly with the supplied NASA OMNI dataset. Its analysis preserves observed measurements, and missing samples break sustained-event detection.

The platform combines historical space-weather analytics, storm investigation, statistical analysis, and interactive mission-control functionality within a single application.

## Our Goal

Our goal is to transform historical space-weather observations into an interactive scientific investigation and operational-awareness experience.

Vexcel examines solar-wind and geomagnetic measurements across a historical timeline spanning 2010–2026, with a particular focus on the May 10–11, 2024 Gannon Superstorm.

By investigating parameters such as interplanetary magnetic field (IMF) Bz, solar-wind speed, dynamic pressure, auroral electrojet activity, and SYM-H, the platform explores how solar-wind conditions relate to geomagnetic disturbances.

The project also introduces a mission-control replay environment that allows users to step through the historical storm observations row by row, monitor changing telemetry, and simulate operator authorization events.

Our objective is to connect scientific data analysis with a more interactive representation of how operators might investigate and respond to significant space-weather events.

## Historical Space-Weather Investigation

A central component of Vexcel is its investigation of historical geomagnetic activity.

The platform includes a 2010–2026 SYM-H timeline that provides a broader perspective on geomagnetic disturbances across the available dataset. The visualization highlights the May 10–11, 2024 storm, when SYM-H reached approximately -497 nT.

A dedicated 48-hour investigation examines the relationship between IMF Bz and SYM-H during the event.

IMF Bz represents the north-south component of the interplanetary magnetic field in geocentric solar magnetospheric (GSM) coordinates. Strongly negative Bz conditions can contribute to geomagnetic activity by enabling more effective coupling between the solar wind and Earth's magnetosphere.

SYM-H provides a high-resolution measure of geomagnetic disturbances associated with changes in Earth's magnetic field.

By comparing these measurements, Vexcel investigates how changes in upstream solar-wind conditions relate to subsequent geomagnetic responses and explores the potential early-warning significance of negative Bz observations.

## Statistical Analysis and Correlation

Vexcel also includes a correlation heatmap that examines relationships between four important space-weather parameters:

- Solar-wind speed.
- Dynamic pressure.
- IMF Bz GSM.
- Auroral electrojet (AE) index.

Using pairwise-complete Pearson correlation, the analysis evaluates linear associations between available observations while accounting for missing values.

These relationships help users investigate how different solar-wind conditions and geomagnetic indicators vary together.

However, correlation does not establish causation. The heatmap is intended to support scientific investigation rather than establish predictive or causal relationships.

## Mission Control and Telemetry Replay

An important feature of Vexcel is its interactive Mission Control environment.

Rather than displaying a predefined animation, the platform performs backend-authoritative, row-by-row replay using the historical NASA OMNI observations.

Operators can interact with the replay through:

- Play and pause controls.
- Reset and individual-step controls.
- Timeline seeking.
- Adjustable playback speeds of 1x, 2x, 5x, and 10x.
- Live telemetry and operational status indicators.

The system evaluates changing measurements against demonstration thresholds to provide an operational interpretation of geomagnetic conditions.

These indicators include NOMINAL, WARNING, and CRITICAL G5 SUPERSTORM states. The thresholds are intended for demonstration purposes and do not represent official NOAA storm classifications.

By allowing users to navigate the historical event interactively, Mission Control provides a more engaging way to understand how measured space-weather conditions evolved throughout the storm.

## Hardware Integration and Operator Authorization

Vexcel extends its mission-control experience through a physical Raspberry Pi Zero W v1.1 hardware interface.

The project explores how historical telemetry and operator authorization events can be connected to a separate physical device.

Through the SAFE MODE CONFIRMATION mechanism, an operator can authorize one of two simulated responses. The system records a UTC event ID and the corresponding replay state.

Authorized events are transmitted to authenticated Raspberry Pi clients, where a blue LED indicates authorization.

The hardware architecture separates the browser, backend, and physical device. The frontend does not access GPIO directly. Instead, the Raspberry Pi runs a dedicated device agent that establishes an authenticated WebSocket connection with the backend.

This connection supports device heartbeats, LED state updates, commands, and acknowledgements.

The SAFE MODE mechanism is a simulation and does not perform electrical switching, disconnect grid transformers, or issue actual spacecraft commands.

## NASA OMNI Dataset and Data Integrity

Vexcel uses the supplied NASA OMNI five-minute CSV dataset:

`nasa_omni_solar_wind_storms_5min_2010-2026.csv`

The dataset contains historical solar-wind, interplanetary magnetic field, and geomagnetic measurements.

Its columns include:

| Parameter | Description |
|---|---|
| `datetime_utc` | UTC observation timestamp |
| `bt_nT` | Total interplanetary magnetic field magnitude |
| `bz_gsm_nT` | North-south IMF component in GSM coordinates |
| `by_gsm_nT` | Y-component of the IMF in GSM coordinates |
| `speed_km_s` | Solar-wind speed |
| `density_cm3` | Solar-wind particle density |
| `temp_K` | Solar-wind plasma temperature |
| `pressure_nPa` | Solar-wind dynamic pressure |
| `efield_mV_m` | Convective solar-wind electric field |
| `ae_nT` | Auroral electrojet index |
| `al_nT` | Lower auroral electrojet index |
| `sym_h_nT` | High-resolution geomagnetic disturbance index |
| `pcn` | Polar Cap North geomagnetic index |
| `proton_flux_10mev` | Energetic proton flux measurement |

An important design principle is that Vexcel does not synthesize missing observations.

Sustained-event detection uses three consecutive five-minute samples, representing a 15-minute period, below either Bz -10 nT or SYM-H -100 nT. Missing samples break the consecutive observation requirement.

This ensures that missing measurements are not incorrectly treated as continuous observations when identifying sustained geomagnetic conditions.

## Architecture

Vexcel is built around three interconnected components:

**1. Backend and scientific processing**

The backend processes the NASA OMNI dataset, provides historical analytics, evaluates telemetry conditions, and maintains the authoritative mission-control replay state.

It also handles hardware authentication, device status, operator authorization events, and WebSocket communication with connected Raspberry Pi clients.

**2. Interactive frontend**

The frontend provides four client-side analysis sections covering historical space-weather analytics, storm investigation, statistical relationships, and Mission Control.

It also includes a shared Hardware Control Dock that communicates with authenticated backend endpoints for device status and hardware commands.

**3. Raspberry Pi hardware client**

A dedicated Python device agent runs on the Raspberry Pi Zero W v1.1.

It establishes an authenticated WebSocket connection to the backend, reports heartbeats, receives commands, updates the LED state, and acknowledges operations.

This separation keeps physical hardware communication independent of the browser and centralizes device coordination within the backend.

## Running the Project

### Backend

```bash
cd backend

python -m venv .venv
. .venv/bin/activate

pip install -r requirements.txt

PYTHONPATH=src uvicorn spaceweather.main:app --reload
