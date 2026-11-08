"""Solar Sentinel: space weather intelligence from NASA OMNI solar wind data.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import importlib
import os
import time
from datetime import datetime
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import theme

# Streamlit reruns app.py on every change but keeps imported modules cached, so edits to theme.py
# (e.g. a new colour key) would not be seen until a full server restart. Reloading keeps them in sync.
theme = importlib.reload(theme)

st.set_page_config(page_title="Solar Sentinel", page_icon="🛰️", layout="wide")

# ---------------------------------------------------------------------------
# Configuration: every threshold used in the analysis is defined here
# ---------------------------------------------------------------------------
DATA_PATH = "nasa_omni_solar_wind_storms_5min_2010-2026.csv"
COLS = ["datetime_utc", "bz_gsm_nT", "sym_h_nT", "speed_km_s", "density_cm3", "pressure_nPa", "ae_nT"]

EVENT_START = pd.Timestamp("2024-05-10 00:00")
EVENT_END = pd.Timestamp("2024-05-12 00:00")

HEADLINE_BZ_NT = -30          # southward Bz precursor threshold used for the headline finding
HEADLINE_SYMH_NT = -250       # ground disturbance threshold used for the headline finding
GAP_TOLERANCE_MIN = 10        # an episode may contain up to 10 min of samples above threshold / missing
SAMPLE_MIN = 5                # dataset cadence

INTENSE_SYMH_NT = -100        # common research convention for an "intense" storm
SUPERINTENSE_SYMH_NT = -250   # common research convention for a "superintense" storm
EVENT_SEPARATION = pd.Timedelta(hours=24)
CYCLE_25_START = pd.Timestamp("2019-12-01")  # Solar Cycle 24/25 minimum (SILSO; NASA-NOAA prediction panel)

SIM_BZ_WARNING_NT = -20       # simulator early-warning trigger (deliberately more sensitive)
SIM_SYMH_CRITICAL_NT = -250   # simulator critical trigger

# Raspberry Pi integration point. The hardware console signals a physical
# confirmation by creating or touching this file (see README). Only a signal
# written *after* the operator's request counts.
HW_SIGNAL_PATH = Path(os.environ.get("SENTINEL_HW_SIGNAL", "hardware_confirm.signal"))
HW_POLL_SECONDS = 2


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def nt(value: float, decimals: int = 0) -> str:
    """Format a value in nT with a true minus sign."""
    if pd.isna(value):
        return "No data"
    return f"{value:.{decimals}f}".replace("-", "−") + " nT"


def signed(value: float) -> str:
    return f"{value:g}".replace("-", "−")


def duration(minutes: float | None) -> str:
    if minutes is None:
        return "n/a"
    minutes = int(round(minutes))
    hours, mins = divmod(minutes, 60)
    if hours == 0:
        return f"{mins} min"
    return f"{hours} h {mins} min" if mins else f"{hours} h"


def utc(ts: pd.Timestamp, with_date: bool = False) -> str:
    return ts.strftime("%b %-d, %H:%M UTC") if with_date else ts.strftime("%H:%M UTC")


def html(markup: str) -> None:
    st.html("\n".join(line.strip() for line in markup.strip().splitlines()))


def status_banner(kind: str, label: str, message: str, icon: str) -> None:
    """kind: crit | warn | ok | info. The label text carries the meaning; colour reinforces it."""
    html(f"""
    <div class="ss-status {kind}" role="status">
      <span class="ss-status-icon" aria-hidden="true">{icon}</span>
      <div><p class="ss-status-label">{label}</p><p class="ss-status-msg">{message}</p></div>
    </div>""")


def question_header(question: str, finding: str, purpose: str = "") -> None:
    """Section opener for the guided story: the question it answers, then the answer."""
    purpose_html = f'<p class="ss-purpose">{purpose}</p>' if purpose else ""
    html(f'<p class="ss-question">{question}</p><h2 class="ss-section-title">{finding}</h2>{purpose_html}')


def card(label: str, value: str, note: str = "", accent: str | None = None) -> str:
    style = f' style="border-left-color:{accent}"' if accent else ""
    cls = "ss-card ss-primary" if accent else "ss-card"
    note_html = f'<p class="ss-card-note">{note}</p>' if note else ""
    return (f'<div class="{cls}"{style}><p class="ss-card-label">{label}</p>'
            f'<p class="ss-card-value">{value}</p>{note_html}</div>')


# ---------------------------------------------------------------------------
# Data loading and cached preprocessing
# (cached functions take no DataFrame argument, so nothing large is re-hashed)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_data() -> pd.DataFrame | None:
    if not os.path.exists(DATA_PATH):
        return None
    df = pd.read_csv(DATA_PATH, usecols=COLS)
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], format="%Y-%m-%d %H:%M")
    return df.sort_values("datetime_utc").reset_index(drop=True)


@st.cache_data(show_spinner=False)
def storm_window() -> pd.DataFrame:
    """May 10–11, 2024 5-minute records with valid Bz and SYM-H."""
    df = load_data()
    mask = (df["datetime_utc"] >= EVENT_START) & (df["datetime_utc"] <= EVENT_END)
    return df[mask].dropna(subset=["sym_h_nT", "bz_gsm_nT"]).reset_index(drop=True)


def _episode_onset(times: pd.Series, gap_min: int) -> pd.Timestamp:
    """Start of the most recent run of below-threshold samples, tolerating short gaps."""
    max_step = pd.Timedelta(minutes=SAMPLE_MIN + gap_min)
    onset = times.iloc[-1]
    for prev in reversed(times.iloc[:-1].tolist()):
        if onset - prev <= max_step:
            onset = prev
        else:
            break
    return onset


@st.cache_data(show_spinner=False)
def lead_time_analysis(bz_thr: float, symh_thr: float) -> dict | None:
    """Measure the observed lead time between a southward-Bz episode and a SYM-H threshold crossing.

    1. t_ground: first 5-min sample with SYM-H <= symh_thr.
    2. Bz samples at or before t_ground with Bz <= bz_thr.
    3. Onset: start of the most recent episode of such samples, allowing up to
       GAP_TOLERANCE_MIN minutes of above-threshold or missing samples inside it.
    4. Lead time = t_ground - onset (from dataset timestamps).
    """
    w = storm_window()
    hits = w.loc[w["sym_h_nT"] <= symh_thr, "datetime_utc"]
    if hits.empty:
        return None
    t_ground = hits.iloc[0]
    below = w.loc[(w["datetime_utc"] <= t_ground) & (w["bz_gsm_nT"] <= bz_thr), "datetime_utc"]
    result = {"t_ground": t_ground, "symh_at_ground": float(w.loc[w["datetime_utc"] == t_ground, "sym_h_nT"].iloc[0])}
    if below.empty:
        return result | {"t_onset": None}

    def minutes(a, b):
        return (b - a).total_seconds() / 60

    t_onset = _episode_onset(below, GAP_TOLERANCE_MIN)
    t_strict = _episode_onset(below, 0)
    t_first = below.iloc[0]
    last_below = below.iloc[-1]
    return result | {
        "t_onset": t_onset,
        "lead_min": minutes(t_onset, t_ground),
        "t_strict": t_strict,
        "strict_min": minutes(t_strict, t_ground),
        "t_first": t_first,
        "first_min": minutes(t_first, t_ground),
        "active_at_crossing": minutes(last_below, t_ground) <= SAMPLE_MIN + GAP_TOLERANCE_MIN,
        "ended_before_min": minutes(last_below, t_ground),
    }


@st.cache_data(show_spinner=False)
def history() -> dict:
    """Daily overview, storm event catalogue and solar-cycle comparison for 2010–2026."""
    df = load_data()
    symh = df.set_index("datetime_utc")["sym_h_nT"]

    daily = symh.resample("D").min().rename("min_symh").to_frame()
    daily.index.name = "date"

    # Storm events: samples at or below the intense threshold, split where the gap exceeds 24 h.
    below_t = symh.index[(symh <= INTENSE_SYMH_NT).to_numpy()]
    new_event = np.r_[True, np.diff(below_t.values) > EVENT_SEPARATION.to_timedelta64()]
    rows = []
    for _, times in pd.Series(below_t).groupby(np.cumsum(new_event)):
        seg = symh.loc[times.iloc[0]:times.iloc[-1]]
        rows.append({"start": times.iloc[0], "peak": seg.idxmin(), "min_symh": float(seg.min())})
    events = pd.DataFrame(rows)
    events["cycle"] = np.where(events["peak"] < CYCLE_25_START, 24, 25)
    events["year"] = events["peak"].dt.year

    first, last = df["datetime_utc"].min(), df["datetime_utc"].max()
    year_len = pd.Timedelta(days=365.25)
    cycles = {}
    for cyc, (a, b) in {24: (first, CYCLE_25_START), 25: (CYCLE_25_START, last)}.items():
        ev = events[events["cycle"] == cyc]
        years = (b - a) / year_len
        strongest = ev.loc[ev["min_symh"].idxmin()]
        cycles[cyc] = {
            "start": a, "end": b, "years": years,
            "intense": len(ev), "rate": len(ev) / years,
            "superintense": int((ev["min_symh"] <= SUPERINTENSE_SYMH_NT).sum()),
            "strongest": strongest["min_symh"], "strongest_at": strongest["peak"],
        }

    annual = (events.assign(superintense=events["min_symh"] <= SUPERINTENSE_SYMH_NT)
              .groupby("year").agg(intense=("min_symh", "size"), superintense=("superintense", "sum"))
              .reindex(range(first.year, last.year + 1), fill_value=0))
    return {"daily": daily, "events": events, "cycles": cycles, "annual": annual,
            "first": first, "last": last, "records": len(df)}


def read_hardware_signal() -> float | None:
    """Epoch time of the most recent physical confirmation from the hardware console, or None."""
    try:
        return HW_SIGNAL_PATH.stat().st_mtime
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Header, theme toggle and key finding
# ---------------------------------------------------------------------------
head_left, head_right = st.columns([5, 1], vertical_alignment="center")
with head_right:
    with st.container(horizontal_alignment="right"):
        light = st.toggle("Light mode", key="light", bind="query-params",
                          help="Switch between the dark (default) and light colour themes.")
T = theme.LIGHT if light else theme.DARK
st.html(theme.css(T))

with head_left:
    html("""
    <h1 class="ss-title">Solar Sentinel</h1>
    <p class="ss-subtitle">Space weather intelligence from 16 years of NASA solar wind observations</p>
    """)

with st.spinner("Loading 1.7 million NASA OMNI records…"):
    df = load_data()

if df is None:
    status_banner("crit", "Dataset not found",
                  f"Cannot find <code>{DATA_PATH}</code>. Place the unzipped <code>2_Space_Weather</code> "
                  "CSV in the repository root and reload.", "!")
    st.stop()

win = storm_window()
hist = history()
headline = lead_time_analysis(HEADLINE_BZ_NT, HEADLINE_SYMH_NT)
storm_min_row = win.loc[win["sym_h_nT"].idxmin()]
headline_lead = headline["lead_min"] if headline and headline.get("t_onset") is not None else None

if headline_lead is not None:
    html(f"""
    <section class="ss-hero ss-hero-single" aria-label="Key finding">
      <p class="ss-kpi"><span class="ss-kpi-value">{int(round(headline_lead))}</span><span class="ss-kpi-unit">min</span></p>
      <div>
        <h2 class="ss-hero-headline">Space showed danger {int(round(headline_lead))} minutes before Earth's magnetic field hit an extreme level</h2>
        <p class="ss-hero-text">In NASA data from the May 2024 superstorm, a steady danger signal in the solar wind
          came first. Notice like this could help operators protect power grids and satellites.</p>
        <p class="ss-hero-note">Observed in one historical storm, not a tested forecast.</p>
      </div>
    </section>""")

tab_label = f"The {int(round(headline_lead))}-Minute Warning" if headline_lead is not None else "The Early Warning"
tab1, tab2, tab3 = st.tabs([tab_label, "16 Years of Solar Activity", "Mission Control Simulator"])


# ---------------------------------------------------------------------------
# Tab 1: The 45-minute warning
# ---------------------------------------------------------------------------
STORY_VIEW = (pd.Timestamp("2024-05-10 17:00"), pd.Timestamp("2024-05-11 03:00"))


def storm_figure(res: dict | None, bz_thr: float, symh_thr: float) -> go.Figure:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.1,
                        subplot_titles=("In space · solar wind (Bz)", "At Earth · magnetic field (SYM-H)"))
    fig.add_trace(go.Scatter(
        x=win["datetime_utc"], y=win["bz_gsm_nT"], name="Bz", mode="lines",
        line=dict(color=T["data"], width=1.8),
        hovertemplate="Bz %{y:.1f} nT<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=win["datetime_utc"], y=win["sym_h_nT"], name="SYM-H", mode="lines",
        line=dict(color=T["data"], width=1.8), fill="tozeroy", fillcolor=T["data_fill"],
        hovertemplate="SYM-H %{y:.0f} nT<extra></extra>"), row=2, col=1)
    theme.style_axes(fig, T)

    label_bg = T["surface"]
    fig.add_hline(y=bz_thr, row=1, col=1, line=dict(color=T["warn"], dash="dash", width=1.5),
                  annotation_text=f"Danger line {signed(bz_thr)} nT", annotation_position="bottom left",
                  annotation_font=dict(color=T["warn_text"], size=12), annotation_bgcolor=label_bg)
    fig.add_hline(y=symh_thr, row=2, col=1, line=dict(color=T["crit"], dash="dash", width=1.5),
                  annotation_text=f"Extreme level {signed(symh_thr)} nT", annotation_position="bottom left",
                  annotation_font=dict(color=T["crit_text"], size=12), annotation_bgcolor=label_bg)

    if res and res.get("t_onset") is not None:
        t0, t1 = res["t_onset"], res["t_ground"]
        # The gap is the visual focus: strong band across both panels, one clear label.
        fig.add_vrect(x0=t0, x1=t1, fillcolor=T["warn_gap"], line_width=0, layer="below", row="all", col=1)
        fig.add_vline(x=t0, line=dict(color=T["warn"], width=2.5), row="all", col=1)
        fig.add_vline(x=t1, line=dict(color=T["crit"], width=2.5), row="all", col=1)
        fig.add_annotation(
            x=t0 + (t1 - t0) / 2, y=0.97, xref="x", yref="y domain", yanchor="top", showarrow=False,
            text=f"<b>{duration(res['lead_min'])}</b>", font=dict(color=T["warn_text"], size=15),
            bgcolor=label_bg, bordercolor=T["warn"], borderwidth=1.5, borderpad=4)
        bz0 = float(win.loc[win["datetime_utc"] == t0, "bz_gsm_nT"].iloc[0])
        fig.add_trace(go.Scatter(
            x=[t0], y=[bz0], mode="markers", name="Danger signal",
            marker=dict(symbol="diamond", size=12, color=T["warn"], line=dict(color=T["surface"], width=1.5)),
            hovertemplate=f"Danger signal holds from {utc(t0)}<extra></extra>"), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=[t1], y=[res["symh_at_ground"]], mode="markers", name="Extreme level",
            marker=dict(symbol="square", size=11, color=T["crit"], line=dict(color=T["surface"], width=1.5)),
            hovertemplate=f"Earth reaches {signed(symh_thr)} nT at {utc(t1)}<extra></extra>"), row=2, col=1)
        # Keep the earlier, brief dip visible (muted) so the chart doesn't imply the signal first appeared at t0.
        if res["t_first"] < t0:
            tf = res["t_first"]
            bzf = float(win.loc[win["datetime_utc"] == tf, "bz_gsm_nT"].iloc[0])
            fig.add_annotation(
                x=tf, y=bzf, xref="x", yref="y", showarrow=True, arrowhead=0, arrowcolor=T["muted"],
                ax=0, ay=34, text=f"Brief earlier dip {tf:%H:%M}", font=dict(color=T["muted"], size=11),
                bgcolor=label_bg)

    t_min = storm_min_row["datetime_utc"]
    fig.add_annotation(
        x=t_min, y=storm_min_row["sym_h_nT"], xref="x2", yref="y2", showarrow=True, arrowhead=0,
        arrowcolor=T["muted"], ax=-50, ay=-8, text=f"Storm peak {nt(storm_min_row['sym_h_nT'])}",
        font=dict(color=T["muted"], size=11), bgcolor=label_bg)

    fig.update_layout(**theme.plot_layout(T, 540, hovermode="x unified", hoversubplots="axis"))
    fig.update_xaxes(range=list(STORY_VIEW), hoverformat="%b %d, %H:%M UTC")
    fig.update_xaxes(title_text="Time (UTC)", row=2, col=1)
    fig.update_yaxes(title_text="nT", row=1, col=1)
    fig.update_yaxes(title_text="nT", row=2, col=1)
    return fig


def sequence_strip(res: dict) -> None:
    """21:00 danger signal → gap → 21:45 extreme level, as a readable sequence above the chart."""
    html(f"""
    <ol class="ss-sequence" aria-label="Sequence of events">
      <li class="ss-seq-warn"><span class="ss-seq-time">{res['t_onset']:%H:%M} UTC</span>
        <span class="ss-seq-label">Steady danger signal in space</span></li>
      <li class="ss-seq-arrow" aria-hidden="true">→</li>
      <li class="ss-seq-gap"><span class="ss-seq-time">{duration(res['lead_min'])}</span>
        <span class="ss-seq-label">observed gap</span></li>
      <li class="ss-seq-arrow" aria-hidden="true">→</li>
      <li class="ss-seq-crit"><span class="ss-seq-time">{res['t_ground']:%H:%M} UTC</span>
        <span class="ss-seq-label">Earth's field hits extreme level</span></li>
    </ol>""")


with tab1:
    question_header(
        "1 · What did we discover?",
        "A steady danger signal in space came first",
        "Top: solar wind measured by spacecraft. Bottom: Earth's magnetic field measured on the ground. "
        "Same storm, May 10, 2024.",
    )

    # Threshold state lives in session_state, so the chart above the controls can use it.
    bz_thr = st.session_state.get("bz_thr", HEADLINE_BZ_NT)
    symh_thr = st.session_state.get("symh_thr", HEADLINE_SYMH_NT)
    res = lead_time_analysis(bz_thr, symh_thr)
    has_lead = bool(res and res.get("t_onset") is not None)
    is_headline = (bz_thr, symh_thr) == (HEADLINE_BZ_NT, HEADLINE_SYMH_NT)

    if has_lead:
        sequence_strip(res)
        if not is_headline:
            st.caption(f"Showing your thresholds: danger line {signed(bz_thr)} nT, extreme level {signed(symh_thr)} nT. "
                       f"The headline uses {signed(HEADLINE_BZ_NT)} nT and {signed(HEADLINE_SYMH_NT)} nT.")
    elif res:
        status_banner("info", "No danger signal found",
                      f"Bz never reached {signed(bz_thr)} nT before SYM-H reached {signed(symh_thr)} nT.", "i")
    else:
        status_banner("info", "Extreme level not reached",
                      f"SYM-H never reached {signed(symh_thr)} nT during May 10–11, 2024.", "i")

    alt_text = (
        "Two stacked line charts for May 10 to 11, 2024. Top: solar wind magnetic field Bz. Bottom: Earth's "
        "magnetic disturbance SYM-H. "
        + (f"A shaded band marks the {duration(res['lead_min'])} between {utc(res['t_onset'])}, when Bz stays "
           f"at or below {signed(bz_thr)} nT, and {utc(res['t_ground'])}, when SYM-H reaches {signed(symh_thr)} nT. "
           if has_lead else "")
        + f"The storm peaks at {nt(storm_min_row['sym_h_nT'])} at {utc(storm_min_row['datetime_utc'], True)}."
    )
    st.plotly_chart(storm_figure(res, bz_thr, symh_thr), theme=None, config=theme.PLOTLY_CONFIG,
                    alt=alt_text, key="storm_chart")
    if has_lead and res["t_first"] < res["t_onset"]:
        st.caption(f"Earlier dips, like the one at {res['t_first']:%H:%M}, came and went. A dip alone means higher "
                   "risk, not a certain extreme storm. Double-click the chart to see all 48 hours.")

    with st.expander("Explore warning thresholds"):
        c1, c2 = st.columns(2)
        c1.segmented_control(
            "Danger line in space (Bz)", [-20, -25, -30, -35], default=HEADLINE_BZ_NT, required=True,
            format_func=lambda v: f"{signed(v)} nT", key="bz_thr",
            help="How strongly southward the solar wind field must be to count as dangerous. Headline: −30 nT.")
        c2.segmented_control(
            "Extreme level at Earth (SYM-H)", [-100, -150, -200, -250], default=HEADLINE_SYMH_NT, required=True,
            format_func=lambda v: f"{signed(v)} nT", key="symh_thr",
            help="How disturbed Earth's field must be to count as extreme. Headline: −250 nT.")
        if has_lead and not res["active_at_crossing"]:
            st.caption(f"With these thresholds, the danger signal had ended "
                       f"{duration(res['ended_before_min'])} before the extreme level.")
        st.caption("Why the gap changes: a stricter danger line (e.g. −35 nT) is met later and less steadily. "
                   "A milder extreme level (e.g. −100 nT) is reached earlier, so a different danger episode comes "
                   "just before it.")

    with st.expander("What do Bz and SYM-H mean?"):
        st.markdown("""
- **Bz** is the north–south direction of the magnetic field carried by the solar wind, measured by spacecraft
  upstream of Earth. When it points strongly south (large negative values), solar wind energy can pour into
  Earth's magnetic field.
- **SYM-H** is built from magnetometers on the ground around the world. It shows how strongly Earth's magnetic
  field is disturbed. More negative values mean a stronger storm, and the currents that can affect power grids.
- Both are measured in nanotesla (nT), a unit of magnetic field strength.
""")

    total_slots = int((EVENT_END - EVENT_START) / pd.Timedelta(minutes=SAMPLE_MIN)) + 1
    missing_slots = total_slots - len(win)
    sim_first = lead_time_analysis(SIM_BZ_WARNING_NT, HEADLINE_SYMH_NT)
    with st.expander("How we measured the gap"):
        st.markdown(f"""
1. **Extreme time:** the first 5-minute measurement where SYM-H is at or below the extreme level.
2. **Danger measurements:** every earlier measurement where Bz is at or below the danger line.
3. **Start of the signal:** the start of the last unbroken run of danger measurements before the extreme time.
   Up to {GAP_TOLERANCE_MIN} minutes of readings just above the line (or missing) are allowed inside a run, so
   one brief flicker does not split it.
4. **Gap** = extreme time − start of the signal, using the dataset's own timestamps.
""")
        if has_lead:
            rows = [
                ("Last unbroken run, 10-minute flickers allowed (headline method)", res["t_onset"], res["lead_min"]),
                ("Last unbroken run, no flickers allowed", res["t_strict"], res["strict_min"]),
                ("First time Bz crossed the line at all", res["t_first"], res["first_min"]),
            ]
            body = "".join(f"<tr><td>{escape(n)}</td><td class='num'>{utc(t)}</td><td class='num'>{duration(m)}</td></tr>"
                           for n, t, m in rows)
            html(f"""<div class="ss-table-wrap"><table class="ss-table">
            <caption>Same data, different definitions (Bz ≤ {signed(bz_thr)} nT, SYM-H ≤ {signed(symh_thr)} nT).
            The headline uses the first row: the steady signal, not the first brief dip.</caption>
            <thead><tr><th scope="col">How the start is defined</th><th scope="col" class="num">Start</th>
            <th scope="col" class="num">Gap</th></tr></thead><tbody>{body}</tbody></table></div>""")

        if sim_first and sim_first.get("t_first") is not None and headline_lead is not None:
            st.markdown(f"""
**Why the simulator warns earlier ({utc(sim_first['t_first'])})**

| | Threshold | Rule | Start |
|---|---|---|---|
| {int(round(headline_lead))}-minute headline | Bz ≤ {signed(HEADLINE_BZ_NT)} nT | Last unbroken run before Earth reaches {signed(HEADLINE_SYMH_NT)} nT | {utc(headline['t_onset'])} |
| Simulator alarm | Bz ≤ {signed(SIM_BZ_WARNING_NT)} nT | Any single 5-minute reading | {utc(sim_first['t_first'])} |

The simulator is a more sensitive alarm that switches off whenever Bz recovers. The headline asks a narrower
question: how long did a *steady*, strong signal last? With −20 nT and the headline's method, the signal would
start at {utc(sim_first['t_onset'])} ({duration(sim_first['lead_min'])}). Neither is a forecast.
""")
        st.markdown(f"""
**Assumptions and limitations**
- NASA's OMNI dataset shifts spacecraft measurements in time to when the solar wind reaches Earth's
  magnetic boundary (the bow shock). The gap is therefore measured from arrival near Earth. A spacecraft
  at the L1 point sees the same conditions earlier, typically by tens of minutes.
- This is one storm. Without testing many storms, including false alarms, it shows what happened, not how
  reliable a forecast would be.
- −30 nT and −250 nT are thresholds chosen for this analysis. −100 nT and −250 nT are common research
  conventions for "intense" and "superintense" storms. They are **not** NOAA G-scale levels, which use the Kp index.
- {missing_slots} of the {total_slots} five-minute slots in this window have missing Bz or SYM-H. They are
  excluded and count toward the flicker allowance.
""")


# ---------------------------------------------------------------------------
# Tab 2: 16 years of solar activity
# ---------------------------------------------------------------------------
cycles = hist["cycles"]
c24, c25 = cycles[24], cycles[25]
events = hist["events"]
STRONG_LABEL = "Strong storm"     # plain-language name for SYM-H <= -100 nT ("intense" in research usage)
EXTREME_LABEL = "Extreme storm"   # plain-language name for SYM-H <= -250 nT ("superintense" in research usage)


@st.cache_data(show_spinner=False)
def rate_sensitivity() -> list[tuple[int, float, float]]:
    """Storm rates per cycle when storms closer than `sep` hours are merged, for several `sep` values."""
    df_ = load_data()
    symh = df_.set_index("datetime_utc")["sym_h_nT"]
    below_t = symh.index[(symh <= INTENSE_SYMH_NT).to_numpy()]
    out = []
    for sep in (6, 12, 24, 48):
        new = np.r_[True, np.diff(below_t.values) > np.timedelta64(sep, "h")]
        peaks = pd.Series([symh.loc[g.iloc[0]:g.iloc[-1]].idxmin()
                           for _, g in pd.Series(below_t).groupby(np.cumsum(new))])
        out.append((sep, (peaks < CYCLE_25_START).sum() / c24["years"], (peaks >= CYCLE_25_START).sum() / c25["years"]))
    return out


def timeline_figure() -> go.Figure:
    daily = hist["daily"]
    fig = go.Figure()
    fig.add_vrect(x0=CYCLE_25_START, x1=hist["last"], fillcolor=T["cycle_band"], line_width=0, layer="below")
    fig.add_trace(go.Scatter(
        x=daily.index, y=daily["min_symh"], mode="lines", name="Daily low",
        line=dict(color=T["data"], width=1), connectgaps=False,
        hovertemplate="%{x|%b %d, %Y}<br>Lowest SYM-H that day: %{y:.0f} nT<extra></extra>"))
    theme.style_axes(fig, T)

    fig.add_hline(y=INTENSE_SYMH_NT, line=dict(color=T["warn"], dash="dash", width=1.2),
                  annotation_text=f"{STRONG_LABEL} ({signed(INTENSE_SYMH_NT)} nT)", annotation_position="bottom left",
                  annotation_font=dict(color=T["warn_text"], size=12), annotation_bgcolor=T["surface"])
    fig.add_hline(y=SUPERINTENSE_SYMH_NT, line=dict(color=T["crit"], dash="dash", width=1.2),
                  annotation_text=f"{EXTREME_LABEL} ({signed(SUPERINTENSE_SYMH_NT)} nT)",
                  annotation_position="bottom left",
                  annotation_font=dict(color=T["crit_text"], size=12), annotation_bgcolor=T["surface"])
    fig.add_vline(x=CYCLE_25_START, line=dict(color=T["muted"], width=1, dash="dot"))
    for x, text in [(hist["first"], "Solar Cycle 24"), (CYCLE_25_START, "Solar Cycle 25 (ongoing)")]:
        fig.add_annotation(x=x, y=1, xref="x", yref="paper", yanchor="bottom", xanchor="left", xshift=4,
                           showarrow=False, text=f"<b>{text}</b>", font=dict(color=T["text"], size=12))

    big = events[events["min_symh"] <= SUPERINTENSE_SYMH_NT]
    strongest_24 = events[events["cycle"] == 24].nsmallest(1, "min_symh")
    marked = pd.concat([big, strongest_24])
    fig.add_trace(go.Scatter(
        x=marked["peak"], y=marked["min_symh"], mode="markers", name="Labelled storms",
        marker=dict(size=8, color=T["surface"], line=dict(color=T["crit"], width=2)),
        hovertemplate="%{x|%b %d, %Y %H:%M UTC}<br>Storm peak %{y:.0f} nT<extra></extra>"))
    ordered = list(marked.sort_values("peak").itertuples())
    for i, ev in enumerate(ordered):
        if ev.peak.date() == pd.Timestamp("2024-05-11").date():
            label = f"May 2024 storm<br>(our case study)<br>{nt(ev.min_symh)}"
        elif ev.cycle == 24:
            label = f"Cycle 24's strongest<br>{ev.peak:%b %Y} · {nt(ev.min_symh)}"
        else:
            label = f"{ev.peak:%b %Y}<br>{nt(ev.min_symh)}"
        # Spread labels sideways when two labelled storms are close together in time.
        near_prev = i > 0 and (ev.peak - ordered[i - 1].peak) < pd.Timedelta(days=200)
        near_next = i + 1 < len(ordered) and (ordered[i + 1].peak - ev.peak) < pd.Timedelta(days=200)
        ax = 45 if near_prev else (-45 if near_next else 0)
        fig.add_annotation(x=ev.peak, y=ev.min_symh, text=label,
                           showarrow=True, arrowhead=0, arrowcolor=T["muted"], ax=ax, ay=45,
                           font=dict(color=T["text"], size=11), bgcolor=T["surface"])

    fig.update_layout(**theme.plot_layout(T, 440, hovermode="closest", margin=dict(l=64, r=20, t=44, b=44)))
    fig.update_yaxes(title_text="Lowest SYM-H each day (nT)", range=[min(-580, daily["min_symh"].min() - 90), 60])
    fig.update_xaxes(showspikes=False)
    return fig


def annual_figure() -> go.Figure:
    annual = hist["annual"]
    years = annual.index.to_numpy()
    partial = annual.index == hist["last"].year
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=years, y=annual["intense"] - annual["superintense"], name=STRONG_LABEL,
        marker=dict(color=[T["data_soft"] if p else T["data"] for p in partial],
                    line=dict(color=T["data"], width=[1.5 if p else 0 for p in partial])),
        hovertemplate="%{x}: %{y} strong storms<extra></extra>"))
    fig.add_trace(go.Bar(
        x=years, y=annual["superintense"], name=EXTREME_LABEL,
        marker=dict(color=T["crit"]), hovertemplate="%{x}: %{y} extreme storms<extra></extra>"))
    theme.style_axes(fig, T)
    # Cycle boundary (Dec 2019 minimum) drawn between the 2019 and 2020 bars; 2019 had no strong storms.
    boundary = CYCLE_25_START.year - 0.5
    fig.add_vline(x=boundary, line=dict(color=T["muted"], width=1, dash="dot"))
    fig.add_annotation(x=boundary, y=1, yref="paper", xanchor="left", yanchor="top", xshift=4, showarrow=False,
                       text="Cycle 25 →", font=dict(color=T["muted"], size=11))
    fig.add_annotation(x=boundary, y=1, yref="paper", xanchor="right", yanchor="top", xshift=-4, showarrow=False,
                       text="← Cycle 24", font=dict(color=T["muted"], size=11))
    fig.add_annotation(x=years[-1], y=annual["intense"].iloc[-1], text=f"So far<br>(to {hist['last']:%b %-d})",
                       showarrow=False, yanchor="bottom", yshift=4, font=dict(color=T["muted"], size=11))
    fig.update_layout(**theme.plot_layout(
        T, 320, barmode="stack", showlegend=True, hovermode="closest", bargap=0.25,
        title=dict(text="Storms per year", x=0, xanchor="left", font=dict(size=13, color=T["text"]))))
    fig.update_xaxes(showspikes=False, dtick=1, tickformat="d")
    fig.update_yaxes(title_text="Storms")
    return fig


def event_detail_figure(peak: pd.Timestamp) -> go.Figure:
    a, b = peak - pd.Timedelta(hours=36), peak + pd.Timedelta(hours=36)
    i0, i1 = df["datetime_utc"].searchsorted([a, b])
    seg = df.iloc[i0:i1]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.12,
                        subplot_titles=("In space: Bz (nT), every 5 minutes", "At Earth: SYM-H (nT), every 5 minutes"))
    fig.add_trace(go.Scatter(x=seg["datetime_utc"], y=seg["bz_gsm_nT"], line=dict(color=T["data"], width=1.4),
                             hovertemplate="Bz %{y:.1f} nT<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(x=seg["datetime_utc"], y=seg["sym_h_nT"], line=dict(color=T["data"], width=1.4),
                             fill="tozeroy", fillcolor=T["data_fill"],
                             hovertemplate="SYM-H %{y:.0f} nT<extra></extra>"), row=2, col=1)
    theme.style_axes(fig, T)
    fig.add_hline(y=INTENSE_SYMH_NT, row=2, col=1, line=dict(color=T["warn"], dash="dash", width=1))
    fig.add_hline(y=SUPERINTENSE_SYMH_NT, row=2, col=1, line=dict(color=T["crit"], dash="dash", width=1))
    fig.update_layout(**theme.plot_layout(T, 420, hovermode="x unified", hoversubplots="axis"))
    fig.update_xaxes(hoverformat="%b %d, %H:%M UTC")
    return fig


def comparison_figure() -> go.Figure:
    """Two bars: strong storms per year in the observed parts of Cycles 24 and 25."""
    labels = [f"Cycle 24<br><span style='font-size:11px'>{c24['start']:%Y}–{(CYCLE_25_START - pd.Timedelta(days=1)):%Y}</span>",
              f"Cycle 25<br><span style='font-size:11px'>{CYCLE_25_START:%Y}–{c25['end']:%Y} (ongoing)</span>"]
    rates = [c24["rate"], c25["rate"]]
    fig = go.Figure(go.Bar(
        x=rates, y=labels, orientation="h", marker=dict(color=[T["data_soft"], T["data"]]),
        text=[f"<b>{r:.1f}</b> per year" for r in rates], textposition="outside", cliponaxis=False,
        textfont=dict(color=T["text"], size=15, family="IBM Plex Mono, monospace"),
        customdata=[[c24["intense"], c24["years"]], [c25["intense"], c25["years"]]],
        hovertemplate="%{customdata[0]} strong storms in %{customdata[1]:.1f} years<extra></extra>"))
    theme.style_axes(fig, T)
    fig.update_layout(**theme.plot_layout(T, 190, margin=dict(l=12, r=110, t=12, b=12), bargap=0.35,
                                          hovermode="closest"))
    fig.update_xaxes(visible=False, range=[0, max(rates) * 1.05], showspikes=False)
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(color=T["text"], size=13))
    return fig


with tab2:
    ratio = c25["rate"] / c24["rate"]
    ratio_words = "about twice as common" if 1.8 <= ratio <= 2.2 else f"{ratio:.1f}× as common"
    question_header(
        "2 · Is this part of a bigger pattern?",
        f"Strong storms are {ratio_words} in today's solar cycle",
        "The Sun's activity rises and falls in cycles of about 11 years. We counted every strong storm in "
        "16 years of NASA data.",
    )
    extreme_note = (f"All {c25['superintense']} extreme storms in the record happened in Cycle 25."
                    if c24["superintense"] == 0 and c25["superintense"] > 0 else
                    f"Extreme storms: {c24['superintense']} in Cycle 24, {c25['superintense']} in Cycle 25.")
    st.plotly_chart(
        comparison_figure(), theme=None, config={**theme.PLOTLY_CONFIG, "displayModeBar": False},
        key="compare_chart",
        alt=(f"Bar chart: Solar Cycle 24 averaged {c24['rate']:.1f} strong storms per year "
             f"({c24['intense']} in {c24['years']:.1f} years); Solar Cycle 25 so far averaged {c25['rate']:.1f} "
             f"({c25['intense']} in {c25['years']:.1f} years)."))
    html(f'<p class="ss-compare-note">{extreme_note} <span>We only have part of Cycle 24, and Cycle 25 is not '
         'over, so this compares the periods observed, not complete cycles.</span></p>')

    labelled = events[events["min_symh"] <= SUPERINTENSE_SYMH_NT].sort_values("peak")
    st.plotly_chart(
        timeline_figure(), theme=None, config=theme.PLOTLY_CONFIG, key="timeline_chart",
        alt=(f"Line chart of the lowest daily SYM-H from {hist['first']:%B %Y} to {hist['last']:%B %Y}. "
             f"Extreme storms at or below {signed(SUPERINTENSE_SYMH_NT)} nT are labelled: "
             + "; ".join(f"{e.peak:%B %Y} at {nt(e.min_symh)}" for e in labelled.itertuples())
             + f". The strongest Solar Cycle 24 storm reached {nt(c24['strongest'])} in {c24['strongest_at']:%B %Y}."))
    st.caption(f"Each downward spike is a storm. Every spike below the red line happened in "
               f"{labelled['peak'].min():%B %Y} or later." if c24["superintense"] == 0 and len(labelled) else
               "Each downward spike is a storm.")

    annual = hist["annual"]
    with st.expander("Storms year by year"):
        st.plotly_chart(
            annual_figure(), theme=None, config=theme.PLOTLY_CONFIG, key="annual_chart",
            alt="Stacked bar chart of storms per year. "
                + "; ".join(f"{y}: {r.intense - r.superintense} strong, {r.superintense} extreme"
                            for y, r in annual.iterrows())
                + f". {hist['last'].year} is a partial year.")

    with st.expander("Numbers, method and robustness checks"):
        def row(label, f24, f25):
            return f"<tr><th scope='row'>{label}</th><td class='num'>{f24}</td><td class='num'>{f25}</td></tr>"

        html(f"""<div class="ss-table-wrap"><table class="ss-table">
        <caption>Rates are storms divided by years of data, because the record covers a different length of each cycle.</caption>
        <thead><tr><th scope="col">Metric</th><th scope="col" class="num">Solar Cycle 24 (observed part)</th>
        <th scope="col" class="num">Solar Cycle 25 (to date)</th></tr></thead><tbody>
        {row("Period in this dataset", f"{c24['start']:%b %Y} – {(CYCLE_25_START - pd.Timedelta(days=1)):%b %Y}", f"{c25['start']:%b %Y} – {c25['end']:%b %Y}")}
        {row("Years of data", f"{c24['years']:.1f}", f"{c25['years']:.1f}")}
        {row(f"Strong storms (SYM-H ≤ {signed(INTENSE_SYMH_NT)} nT)", c24['intense'], c25['intense'])}
        {row("Strong storms per year", f"{c24['rate']:.1f}", f"{c25['rate']:.1f}")}
        {row(f"Extreme storms (≤ {signed(SUPERINTENSE_SYMH_NT)} nT)", c24['superintense'], c25['superintense'])}
        {row("Strongest storm", f"{nt(c24['strongest'])} · {c24['strongest_at']:%b %Y}", f"{nt(c25['strongest'])} · {c25['strongest_at']:%b %Y}")}
        </tbody></table></div>""")
        sens = rate_sensitivity()
        body = "".join(f"<tr><td>{sep} hours</td><td class='num'>{r24:.1f}</td><td class='num'>{r25:.1f}</td>"
                       f"<td class='num'>{r25 / r24:.1f}×</td></tr>" for sep, r24, r25 in sens)
        pre = ((events["peak"] >= "2010-01-01") & (events["peak"] < "2015-01-01")).sum()
        post = ((events["peak"] >= "2020-01-01") & (events["peak"] < "2025-01-01")).sum()
        html(f"""<div class="ss-table-wrap"><table class="ss-table">
        <caption>Robustness check: does the result depend on how storms are separated? Storms closer together
        than the gap below count as one.</caption>
        <thead><tr><th scope="col">Merge gap</th><th scope="col" class="num">Cycle 24 / year</th>
        <th scope="col" class="num">Cycle 25 / year</th><th scope="col" class="num">Ratio</th></tr></thead>
        <tbody>{body}</tbody></table></div>""")
        st.markdown(f"""
A rough like-for-like check uses the five years leading up to and including each cycle's peak:
**{pre} strong storms in 2010–2014** (Cycle 24) versus **{post} in 2020–2024** (Cycle 25).
""")

        st.markdown(f"""
**How storms are counted**
- The timeline shows the **lowest SYM-H value of each UTC day**. Using the lowest value keeps each storm's true
  depth, where a daily average would hide it.
- A **storm** is a period with SYM-H at or below {signed(INTENSE_SYMH_NT)} nT. Periods less than 24 hours
  apart count as one storm, dated at its lowest point.
- "Strong" ({signed(INTENSE_SYMH_NT)} nT) and "extreme" ({signed(SUPERINTENSE_SYMH_NT)} nT) are our plain-language
  names for the research conventions "intense" and "superintense" (usually stated for the Dst index). They are
  **not** NOAA G-scale levels, which use the Kp index.
- The cycle boundary is the December 2019 solar minimum. The record starts in January 2010, a year into
  Cycle 24, and Cycle 25 is still in progress.
""")

    with st.expander("Look at a single storm in detail"):
        strong = events[events["min_symh"] <= -200].sort_values("min_symh")
        choice = st.selectbox(
            "Storm", strong.index, key="detail_event",
            format_func=lambda i: f"{strong.loc[i, 'peak']:%b %-d, %Y} · peak {nt(strong.loc[i, 'min_symh'])} · Cycle {strong.loc[i, 'cycle']}")
        peak = strong.loc[choice, "peak"]
        st.plotly_chart(event_detail_figure(peak), theme=None, config=theme.PLOTLY_CONFIG, key="detail_chart",
                        alt=f"5-minute Bz and SYM-H for the 72 hours around the storm peak on {peak:%B %-d, %Y}, "
                            f"which reached {nt(strong.loc[choice, 'min_symh'])}.")
        st.caption(f"72 hours around the storm peak at {utc(peak, True)}. Dashed lines: "
                   f"{signed(INTENSE_SYMH_NT)} nT (strong, amber) and {signed(SUPERINTENSE_SYMH_NT)} nT (extreme, red).")



# ---------------------------------------------------------------------------
# Tab 3: Mission Control Simulator
# ---------------------------------------------------------------------------
def alert_level(row_: pd.Series) -> str:
    """Simulator trigger logic (unchanged): critical at SYM-H <= -250 nT, warning at Bz <= -20 nT."""
    if row_["sym_h_nT"] <= SIM_SYMH_CRITICAL_NT:
        return "crit"
    if row_["bz_gsm_nT"] <= SIM_BZ_WARNING_NT:
        return "warn"
    return "ok"


def storm_level(symh: float) -> tuple[str, str]:
    """How disturbed Earth's field is right now, independent of the warning trigger.
    Uses the common SYM-H/Dst conventions: -50 moderate, -100 intense ("strong"), -250 superintense ("extreme")."""
    if symh <= SUPERINTENSE_SYMH_NT:
        return "Extreme storm", "crit"
    if symh <= INTENSE_SYMH_NT:
        return "Strong storm", "warn"
    if symh <= -50:
        return "Moderate storm", "info"
    return "Quiet", "info"


def playback_figure(current: pd.Timestamp) -> go.Figure:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.14,
                        subplot_titles=("In space: Bz (nT)", "At Earth: SYM-H (nT)"))
    fig.add_trace(go.Scatter(x=win["datetime_utc"], y=win["bz_gsm_nT"], line=dict(color=T["data"], width=1.3),
                             hovertemplate="Bz %{y:.1f} nT<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(x=win["datetime_utc"], y=win["sym_h_nT"], line=dict(color=T["data"], width=1.3),
                             hovertemplate="SYM-H %{y:.0f} nT<extra></extra>"), row=2, col=1)
    theme.style_axes(fig, T)
    fig.add_hline(y=SIM_BZ_WARNING_NT, row=1, col=1, line=dict(color=T["warn"], dash="dash", width=1))
    fig.add_hline(y=SIM_SYMH_CRITICAL_NT, row=2, col=1, line=dict(color=T["crit"], dash="dash", width=1))
    fig.add_vline(x=current, line=dict(color=T["text"], width=1.5), row="all", col=1)
    fig.update_layout(**theme.plot_layout(T, 280, hovermode="x unified", hoversubplots="axis",
                                          margin=dict(l=64, r=20, t=44, b=44)))
    fig.update_xaxes(hoverformat="%b %d, %H:%M UTC", tickformat="%b %d\n%H:%M")
    return fig


if "interlock" not in st.session_state:
    st.session_state.interlock = {"status": "idle"}


def jump_to(ts: datetime) -> None:
    st.session_state.playback_t = ts


with tab3:
    question_header(
        "3 · What could we do with this information?",
        "Act on the warning, with a human check",
        "Drag through the storm. When a warning appears, request protective action.",
    )
    html('<p class="ss-badge"><b>Simulation</b> · replay of real NASA data from May 10–11, 2024 · not live</p>')

    times = [t.to_pydatetime() for t in win["datetime_utc"]]
    first_warn = win.loc[win["bz_gsm_nT"] <= SIM_BZ_WARNING_NT, "datetime_utc"].iloc[0].to_pydatetime()
    first_crit = win.loc[win["sym_h_nT"] <= SIM_SYMH_CRITICAL_NT, "datetime_utc"].iloc[0].to_pydatetime()
    if "playback_t" not in st.session_state:
        st.session_state.playback_t = win.loc[win["datetime_utc"] >= "2024-05-10 17:00", "datetime_utc"].iloc[0].to_pydatetime()

    playback = st.select_slider(
        "Replay time (UTC)", options=times, key="playback_t", format_func=lambda t: t.strftime("%b %d, %H:%M"),
        help="Drag, or use the arrow keys to step 5 minutes.")
    with st.container(horizontal=True, gap="small", vertical_alignment="center"):
        st.caption("Jump to:", width="content")
        st.button(f"First warning ({first_warn:%H:%M})", on_click=jump_to, args=(first_warn,), type="tertiary")
        st.button(f"Extreme level ({first_crit:%H:%M})", on_click=jump_to, args=(first_crit,), type="tertiary")
        st.button(f"Storm peak ({storm_min_row['datetime_utc']:%b %d %H:%M})", on_click=jump_to,
                  args=(storm_min_row["datetime_utc"].to_pydatetime(),), type="tertiary")

    curr = win.loc[win["datetime_utc"] == pd.Timestamp(playback)].iloc[0]
    level = alert_level(curr)
    severity, severity_kind = storm_level(curr["sym_h_nT"])
    trigger_on = curr["bz_gsm_nT"] <= SIM_BZ_WARNING_NT
    speed = "no speed data" if pd.isna(curr["speed_km_s"]) else f"solar wind {curr['speed_km_s']:.0f} km/s"

    # One plain-language status. Storm severity at Earth and the warning trigger in space are kept separate,
    # so a storm still in progress is never shown as "nominal" just because the trigger has switched off.
    if level == "crit":
        status_banner("crit", "Extreme storm at Earth",
                      f"Earth's magnetic field is at an extreme level ({nt(curr['sym_h_nT'])}). "
                      "Conditions like these can drive damaging currents in power grids.", "▲")
    elif level == "warn":
        status_banner("warn", "Early warning: danger signal in space",
                      f"The solar wind is strongly southward ({nt(curr['bz_gsm_nT'], 1)}). "
                      "A stronger storm may follow, but it is not certain.", "◆")
    elif severity_kind == "warn":
        status_banner("warn", "Storm in progress · no new warning",
                      f"Earth's field is still strongly disturbed ({nt(curr['sym_h_nT'])}), but the solar wind "
                      "is not meeting the warning trigger right now.", "◆")
    else:
        status_banner("info", f"{severity} · no warning",
                      "Nothing to act on yet. Try “First warning” above." if severity == "Quiet" else
                      f"Earth's field is mildly disturbed ({nt(curr['sym_h_nT'])}). No warning is active.", "●")

    pending = st.session_state.interlock["status"] == "pending"

    @st.fragment(run_every=HW_POLL_SECONDS if pending else None)
    def interlock_panel(level: str, playback_label: str) -> None:
        il = st.session_state.interlock
        if il["status"] == "pending":
            signal = read_hardware_signal()
            if signal is not None and signal > il["requested_at"]:
                il.update(status="confirmed", confirmed_at=signal)
                st.rerun()

        status = il["status"]

        # Progressive disclosure: before a request, show only the action. The step tracker appears once
        # the operator has started the authorisation.
        if status == "idle":
            if level == "ok":
                return
            if st.button("Request protective action", type="primary"):
                il.update(status="pending", requested_at=time.time(), warning_at=playback_label)
                st.rerun()
            st.caption("A second operator must confirm on the physical console before anything engages.")
            return

        def step(cls, state, name, detail):
            return (f'<li class="{cls}"><p class="ss-step-state">{state}</p>'
                    f'<p class="ss-step-name">{name}</p><p class="ss-step-detail">{detail}</p></li>')

        clock = lambda ts: datetime.fromtimestamp(ts).strftime("%H:%M:%S")
        s1 = step("done", "Done", "1 · Warning appears", f"At {il.get('warning_at', playback_label)}")
        s2 = (step("active", "Waiting for console", "2 · Operator requests action",
                   f"Requested at {clock(il.get('requested_at', 0))}") if status == "pending" else
              step("done", "Done", "2 · Operator requests action", f"Requested at {clock(il.get('requested_at', 0))}"))
        if status == "confirmed":
            s3 = step("done", "Received", "3 · Second person confirms", f"On the hardware console at {clock(il['confirmed_at'])}")
            s4 = step("done", "Engaged", "4 · Protective action (simulated)", "Equipment placed in safe mode")
        elif status == "override":
            s3 = step("alert", "Skipped", "3 · Second person confirms", "Software override used instead")
            s4 = step("active", "Engaged (rehearsal)", "4 · Protective action (simulated)", "Without physical confirmation")
        else:
            s3 = step("active", "Waiting", "3 · Second person confirms", "Only the physical console can do this")
            s4 = step("waiting", "Not engaged", "4 · Protective action (simulated)", "Engages after confirmation")

        if status == "pending":
            status_banner("warn", "Waiting for the second operator",
                          "Confirm on the physical console. This page checks for its signal every "
                          f"{HW_POLL_SECONDS} seconds.", "◆")
        elif status == "confirmed":
            status_banner("ok", "Confirmed · protective action engaged (simulated)",
                          "In a real system this could mean switching grid transformers to a protective setup and "
                          "turning satellite solar panels to a safe angle.", "✓")
        else:
            status_banner("warn", "Engaged by software override",
                          "No physical confirmation was received, so this run does not demonstrate the "
                          "two-person rule.", "◆")
        html(f'<ol class="ss-steps" aria-label="Protective action progress">{s1}{s2}{s3}{s4}</ol>')

        if status == "pending":
            if st.button("Cancel request"):
                st.session_state.interlock = {"status": "idle"}
                st.rerun()
            with st.expander("Rehearsing without the hardware console?"):
                st.write("For practice runs only. This engages the simulated action and records that "
                         "**no physical confirmation** took place.")
                if st.button("Engage by software override (no physical confirmation)"):
                    il.update(status="override")
                    st.rerun()
        elif st.button("Reset"):
            st.session_state.interlock = {"status": "idle"}
            st.rerun()

    interlock_panel(level, f"{playback:%b %d, %H:%M} UTC")

    accent = {"crit": T["crit"], "warn": T["warn"], "info": T["border"]}
    html('<div class="ss-cards ss-cards-2">'
         + card("In space · solar wind (Bz)", nt(curr["bz_gsm_nT"], 1),
                f"Warning trigger: <b>{'ON' if trigger_on else 'off'}</b> · {speed}",
                T["warn"] if trigger_on else T["border"])
         + card("At Earth · magnetic field (SYM-H)", nt(curr["sym_h_nT"]),
                f"Storm level: <b>{severity}</b>", accent[severity_kind])
         + "</div>")

    st.plotly_chart(playback_figure(pd.Timestamp(playback)), theme=None, config=theme.PLOTLY_CONFIG,
                    key="playback_chart",
                    alt=f"Bz and SYM-H for May 10 to 11, 2024, with a marker at the replay time {playback:%H:%M} UTC.")

    with st.expander("How the simulator works"):
        st.markdown(f"""
- **Warning trigger (in space):** any 5-minute reading with Bz at or below {signed(SIM_BZ_WARNING_NT)} nT.
  It switches off whenever Bz recovers.
- **Extreme status (at Earth):** SYM-H at or below {signed(SIM_SYMH_CRITICAL_NT)} nT.
- **Storm level** is shown separately: quiet, moderate (≤ −50 nT), strong (≤ {signed(INTENSE_SYMH_NT)} nT) or
  extreme (≤ {signed(SUPERINTENSE_SYMH_NT)} nT). A storm can still be in progress when the trigger is off.
- **Why it warns at {first_warn:%H:%M}, not 21:00:** the simulator's alarm is more sensitive than the
  {duration(headline_lead)} analysis (any single reading at or below {signed(SIM_BZ_WARNING_NT)} nT, instead of a
  steady run at or below {signed(HEADLINE_BZ_NT)} nT). Tab 1 explains the difference.
- **Two-person rule:** the request button is available only during a warning or extreme status. After a
  request, the page checks every {HW_POLL_SECONDS} seconds for a signal from the Raspberry Pi console
  (file: `{HW_SIGNAL_PATH}`). Only a signal written after the request counts as confirmation.
""")


# ---------------------------------------------------------------------------
# Footer: attribution
# ---------------------------------------------------------------------------
html(f"""
<div class="ss-takeaway" style="margin-top:2rem">
<p class="ss-small"><b>Data:</b> NASA/GSFC OMNI 5-minute solar wind and geomagnetic index data
(King &amp; Papitashvili, 2005), Space Physics Data Facility, via
<a href="https://omniweb.gsfc.nasa.gov/" target="_blank" rel="noopener">OMNIWeb</a>.
{hist['records']:,} records, {hist['first']:%b %-d, %Y} – {hist['last']:%b %-d, %Y}.
Solar Sentinel · Sheridan Datathon 2026 · NASA Track.</p>
</div>""")
