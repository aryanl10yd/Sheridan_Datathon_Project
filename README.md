# Solar Sentinel: Early Warning Space Weather & Grid Defense Console

**Sheridan Datathon 2026** — _NASA Track: Beyond Earth (Problem 1: Uncover the Story in the Stars)_  
**Created by:** Aryan, Eric, Terry, Rita

---

## Overview

Modern critical infrastructure—spanning orbital satellite constellations, aviation communications, and high-voltage power transmission grids—is fundamentally vulnerable to extreme space weather. When violent Coronal Mass Ejections (CMEs) impact Earth's magnetosphere, geomagnetically induced currents (GICs) risk catastrophic transformer failure, orbital drag spikes, and satellite telemetry loss.

**Solar Sentinel** is an end-to-end exploratory space physics intelligence platform paired with a physical **Mission Control Early Warning Hardware Console**.

By analyzing 16 years of high-resolution solar wind telemetry from NASA's OMNI database (1.7+ million records from 2010 to 2026), Solar Sentinel uncovers the critical time-lag relationship between deep-space magnetic field orientations and catastrophic geomagnetic ground collapse. The system translates these discoveries into real-time operational risk indicators and actionable defense recommendations for grid operators and satellite engineers.

---

## The Core Data Discovery: The 45-Minute Warning Window

In space weather monitoring, evaluating geomagnetic storms solely by ground-level distortion indices ($SYM\text{-}H$) tells operators what is happening _after_ damage has already commenced.

Using the `nasa_omni_solar_wind_storms_5min_2010-2026.csv` dataset, we performed an in-depth exploratory analysis centering on the historic **May 10–11, 2024 Gannon Superstorm**—the most extreme geomagnetic event in over two decades, which reached a peak $SYM\text{-}H$ of **$-497\text{ nT}$** and triggered auroras visible across Ontario.

### Key Analytical Findings:

1. **The $B_z$ Precursor Flaw:** Earth's geomagnetic field points northward. When the interplanetary magnetic field vector ($B_z$) flips strongly southward (negative), magnetic reconnection opens the magnetosphere, funneling energetic solar plasma directly into Earth's field.
2. **The 30-to-60-Minute Operational Gap:** In the May 2024 event, $B_z$ dropped sharply below **$-30\text{ nT}$** and solar wind velocity surged past **$750\text{ km/s}$** at the L1 Lagrange point **roughly 45 minutes before** the ground-level $SYM\text{-}H$ collapsed past the extreme storm threshold ($-250\text{ nT}$).
3. **The Multi-Variable Signature:** Extreme storm intensity is not driven by wind speed alone, but by the product of sustained southward $B_z$, solar wind dynamic pressure ($P_{dyn}$), and auroral electrojet energy ($AE$).

This 45-minute precursor window provides the missing operational margin required for preventative infrastructure protection.

---

## System Architecture

### Running the dashboard

```bash
pip install streamlit pandas plotly
streamlit run app.py
```

The dataset `nasa_omni_solar_wind_storms_5min_2010-2026.csv` must be in the repository root. Dark mode is the default; the **Light mode** toggle (top right) is also available as `?light=true` in the URL.

### Hardware console integration (Raspberry Pi)

The Mission Control Simulator never marks a physical confirmation itself. After an operator requests safe-mode authorisation, the app checks a signal file every 2 seconds. Only a file written **after** the request counts as physical confirmation.

- Default path: `hardware_confirm.signal` in the repository root
- Override with the `SENTINEL_HW_SIGNAL` environment variable, for example a path on a share mounted from the Pi

Minimal Pi-side example (GPIO button or key switch on pin 17):

```python
from pathlib import Path
from signal import pause
from gpiozero import Button

SIGNAL = Path("hardware_confirm.signal")
key = Button(17)
key.when_pressed = lambda: SIGNAL.touch()
pause()
```

For rehearsals without the hardware, the simulator offers a clearly labelled software override. It records that **no** physical confirmation took place.
