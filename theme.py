"""Design tokens, page CSS and Plotly styling for Solar Sentinel.

Colour meaning is consistent across the app:
    data   (blue)  measured scientific data
    warn   (amber) early-warning signals and thresholds
    crit   (red)   critical conditions
    ok     (green) confirmed / safe / successful states

Every status is also communicated with a text label, so colour is never
the only cue. Text tokens meet WCAG 2.2 AA (4.5:1) on both `bg` and
`surface`; line/marker tokens meet the 3:1 non-text contrast minimum.
"""

from __future__ import annotations

DARK = {
    "name": "dark",
    "bg": "#0B1118",
    "surface": "#18232F",
    "surface_alt": "#111A23",
    "border": "#2E3D4D",
    "grid": "#223140",
    "text": "#E8EEF5",
    "muted": "#B3C0CC",
    "data": "#47B5FF",
    "data_fill": "rgba(71,181,255,0.14)",
    "data_soft": "rgba(71,181,255,0.55)",
    "warn": "#F5B544",
    "warn_text": "#F5B544",
    "warn_bg": "#2B2213",
    "warn_band": "rgba(245,181,68,0.16)",
    "warn_gap": "rgba(245,181,68,0.30)",
    "crit": "#F16D72",
    "crit_text": "#F58C90",
    "crit_bg": "#311A1E",
    "ok": "#4CC38A",
    "ok_text": "#6FD3A2",
    "ok_bg": "#11291F",
    "neutral_bg": "#1D2936",
    "cycle_band": "rgba(232,238,245,0.035)",
}

LIGHT = {
    "name": "light",
    "bg": "#F4F6F9",
    "surface": "#FFFFFF",
    "surface_alt": "#EBEFF4",
    "border": "#C9D3DE",
    "grid": "#E2E8EF",
    "text": "#0F1B28",
    "muted": "#46566A",
    "data": "#0A6BC2",
    "data_fill": "rgba(10,107,194,0.12)",
    "data_soft": "rgba(10,107,194,0.55)",
    "warn": "#B5760A",
    "warn_text": "#875400",
    "warn_bg": "#FFF4DD",
    "warn_band": "rgba(214,145,20,0.16)",
    "warn_gap": "rgba(214,145,20,0.26)",
    "crit": "#CC3740",
    "crit_text": "#A8252E",
    "crit_bg": "#FDECEC",
    "ok": "#1F8A57",
    "ok_text": "#16683F",
    "ok_bg": "#E5F5EC",
    "neutral_bg": "#EBEFF4",
    "cycle_band": "rgba(15,27,40,0.035)",
}

FONT_SANS = "'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', sans-serif"
FONT_MONO = "'IBM Plex Mono', ui-monospace, 'SF Mono', Menlo, monospace"


def css(t: dict) -> str:
    """Page stylesheet for palette `t`, applied over Streamlit's base theme."""
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

.stApp {{
    --bg: {t['bg']}; --surface: {t['surface']}; --surface-alt: {t['surface_alt']};
    --border: {t['border']}; --text: {t['text']}; --muted: {t['muted']};
    --data: {t['data']}; --warn: {t['warn']}; --warn-text: {t['warn_text']};
    --crit: {t['crit']}; --crit-text: {t['crit_text']}; --ok: {t['ok']}; --ok-text: {t['ok_text']};
    --warn-bg: {t['warn_bg']}; --crit-bg: {t['crit_bg']}; --ok-bg: {t['ok_bg']};
    --neutral-bg: {t['neutral_bg']};
    background: var(--bg);
    color: var(--text);
    font-family: {FONT_SANS};
    color-scheme: {t['name']};
}}
[data-testid="stHeader"] {{ background: var(--bg); }}
.stApp p, .stApp li,
.stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stWidgetLabel"] p,
.stApp [data-testid="stCaptionContainer"] {{
    font-family: {FONT_SANS};
}}
.stApp [data-testid="stMarkdownContainer"], .stApp [data-testid="stWidgetLabel"] p,
.stApp [data-testid="stExpander"] summary p {{
    color: var(--text);
}}
.stApp [data-testid="stCaptionContainer"], .stApp [data-testid="stCaptionContainer"] p {{
    color: var(--muted);
}}
.block-container, [data-testid="stMainBlockContainer"] {{ padding-top: 3.75rem; padding-bottom: 3rem; max-width: 1240px; }}

/* ---------- Typography ---------- */
.ss-title {{ font-size: 1.75rem; font-weight: 700; letter-spacing: -0.01em; margin: 0; padding: 0; color: var(--text); line-height: 1.2; }}
.ss-subtitle {{ color: var(--muted); margin: 0.2rem 0 0 0; font-size: 1rem; }}
.ss-section-title {{ font-size: 1.3rem; font-weight: 600; margin: 0.25rem 0 0.2rem 0; padding: 0; color: var(--text); }}
.ss-purpose {{ color: var(--muted); margin: 0 0 0.9rem 0; font-size: 0.98rem; max-width: 75ch; }}
.ss-mono {{ font-family: {FONT_MONO}; }}
.ss-small {{ color: var(--muted); font-size: 0.85rem; }}
.stApp code {{ font-family: {FONT_MONO}; font-size: 0.9em; }}

/* ---------- Key finding ---------- */
.ss-hero {{
    display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); gap: 1.5rem;
    background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 1.4rem 1.5rem; margin: 1rem 0 2rem 0;
}}
.ss-eyebrow {{ color: var(--muted); font-size: 0.78rem; font-weight: 600; letter-spacing: 0.07em; text-transform: uppercase; margin: 0 0 0.5rem 0; }}
.ss-kpi {{ display: flex; align-items: baseline; gap: 0.4rem; margin: 0; }}
.ss-kpi-value {{ font-family: {FONT_MONO}; font-size: 3.2rem; font-weight: 600; line-height: 1; color: var(--warn-text); }}
.ss-kpi-unit {{ font-family: {FONT_MONO}; font-size: 1.5rem; font-weight: 600; color: var(--warn-text); }}
.ss-kpi-label {{ font-size: 1.3rem; font-weight: 600; color: var(--text); margin: 0.35rem 0 0 0; }}
.ss-hero-text {{ margin: 0.75rem 0 0.5rem 0; font-size: 1rem; line-height: 1.55; color: var(--text); max-width: 60ch; }}
.ss-hero-note {{ margin: 0; font-size: 0.85rem; color: var(--muted); }}
.ss-evidence {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.75rem; margin: 0; align-content: center; }}
.ss-evidence > div {{ background: var(--surface-alt); border: 1px solid var(--border); border-radius: 8px; padding: 0.7rem 0.85rem; }}
.ss-evidence dt {{ font-size: 0.8rem; color: var(--muted); margin: 0 0 0.2rem 0; }}
.ss-evidence dd {{ margin: 0; font-family: {FONT_MONO}; font-size: 1.15rem; font-weight: 600; color: var(--text); }}
.ss-evidence dd.ss-sub {{ font-family: {FONT_SANS}; font-size: 0.78rem; font-weight: 400; color: var(--muted); margin-top: 0.15rem; }}

.ss-hero-point {{ margin: 0 0 0.35rem 0; font-size: 0.93rem; color: var(--muted); max-width: 62ch; line-height: 1.5; }}
.ss-hero-point b {{ color: var(--text); }}
.ss-subhead {{ font-size: 1.08rem; font-weight: 600; margin: 1.4rem 0 0.2rem 0; padding: 0; color: var(--text); }}

/* ---------- Comparison (tab 2 headline) ---------- */
.ss-compare {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.75rem; margin: 0.2rem 0 0.8rem 0; }}
.ss-compare-item {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 1rem 1.2rem; }}
.ss-compare-hi {{ border-color: var(--data); }}
.ss-compare-value {{ font-family: {FONT_MONO}; font-size: 2.6rem; font-weight: 600; line-height: 1; margin: 0; color: var(--text); }}
.ss-compare-hi .ss-compare-value {{ color: var(--data); }}
.ss-compare-label {{ margin: 0.3rem 0 0.15rem 0; font-weight: 600; color: var(--text); }}
.ss-compare-sub {{ margin: 0; font-size: 0.85rem; color: var(--muted); }}
.ss-compare-note {{ grid-column: 1 / -1; margin: 0; font-size: 0.93rem; color: var(--text); }}
.ss-compare-note span {{ color: var(--muted); }}
.ss-cards-2 {{ grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }}

/* ---------- Guided story ---------- */
.ss-hero-single {{ grid-template-columns: auto minmax(0, 1fr); align-items: center; gap: 1.75rem; padding: 1.5rem 1.75rem; }}
.ss-hero-single .ss-kpi-value {{ font-size: 4.2rem; }}
.ss-hero-single .ss-kpi-unit {{ font-size: 1.7rem; }}
.ss-hero-headline {{ font-size: 1.4rem; font-weight: 700; line-height: 1.3; margin: 0 0 0.45rem 0; padding: 0; color: var(--text); max-width: 40ch; }}
.ss-question {{ color: var(--data); font-size: 0.8rem; font-weight: 700; letter-spacing: 0.07em; text-transform: uppercase; margin: 1.1rem 0 0.25rem 0; }}
.ss-badge {{ display: inline-block; font-size: 0.82rem; color: var(--muted); border: 1px solid var(--border); border-radius: 999px; padding: 0.2rem 0.7rem; margin: 0 0 0.6rem 0; }}
.ss-badge b {{ color: var(--text); text-transform: uppercase; letter-spacing: 0.06em; font-size: 0.75rem; }}
.ss-sequence {{ list-style: none; display: flex; align-items: stretch; gap: 0.6rem; padding: 0 !important; margin: 0.2rem 0 0.6rem 0 !important; flex-wrap: wrap; }}
.ss-sequence li {{ margin: 0; display: flex; flex-direction: column; justify-content: center; }}
.ss-sequence .ss-seq-warn, .ss-sequence .ss-seq-gap, .ss-sequence .ss-seq-crit {{
    flex: 1 1 160px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 0.65rem 0.9rem; }}
.ss-sequence .ss-seq-warn {{ border-top: 4px solid var(--warn); }}
.ss-sequence .ss-seq-crit {{ border-top: 4px solid var(--crit); }}
.ss-sequence .ss-seq-gap {{ background: var(--warn-bg); border-color: var(--warn); border-width: 2px; }}
.ss-seq-time {{ font-family: {FONT_MONO}; font-size: 1.35rem; font-weight: 600; color: var(--text); line-height: 1.2; }}
.ss-seq-gap .ss-seq-time {{ color: var(--warn-text); font-size: 1.6rem; }}
.ss-seq-label {{ font-size: 0.88rem; color: var(--muted); }}
.ss-seq-arrow {{ color: var(--muted); font-size: 1.3rem; align-self: center; }}

/* ---------- Cards / telemetry ---------- */
.ss-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 0.75rem; margin: 0.5rem 0 0.75rem 0; }}
.ss-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 0.85rem 1rem; }}
.ss-card.ss-primary {{ border-width: 1px 1px 1px 4px; }}
.ss-card .ss-card-label {{ font-size: 0.82rem; color: var(--muted); margin: 0; }}
.ss-card .ss-card-value {{ font-family: {FONT_MONO}; font-size: 1.55rem; font-weight: 600; margin: 0.15rem 0 0.1rem 0; color: var(--text); line-height: 1.2; }}
.ss-card .ss-card-note {{ font-size: 0.8rem; color: var(--muted); margin: 0; }}

/* ---------- Status banners (icon + text label + colour) ---------- */
.ss-status {{
    display: flex; gap: 0.8rem; align-items: flex-start;
    border: 1px solid var(--border); border-left-width: 5px; border-radius: 10px;
    padding: 0.8rem 1rem; margin: 0.5rem 0 0.9rem 0; background: var(--neutral-bg); color: var(--text);
}}
.ss-status .ss-status-icon {{ font-size: 1rem; line-height: 1.45; font-weight: 700; }}
.ss-status .ss-status-label {{ font-weight: 700; letter-spacing: 0.06em; font-size: 0.78rem; margin: 0; text-transform: uppercase; }}
.ss-status .ss-status-msg {{ margin: 0.1rem 0 0 0; font-size: 0.97rem; color: var(--text); }}
.ss-status.crit {{ background: var(--crit-bg); border-color: var(--crit); }}
.ss-status.crit .ss-status-label, .ss-status.crit .ss-status-icon {{ color: var(--crit-text); }}
.ss-status.warn {{ background: var(--warn-bg); border-color: var(--warn); }}
.ss-status.warn .ss-status-label, .ss-status.warn .ss-status-icon {{ color: var(--warn-text); }}
.ss-status.ok {{ background: var(--ok-bg); border-color: var(--ok); }}
.ss-status.ok .ss-status-label, .ss-status.ok .ss-status-icon {{ color: var(--ok-text); }}
.ss-status.info .ss-status-label, .ss-status.info .ss-status-icon {{ color: var(--muted); }}
.ss-status.info {{ border-left-color: var(--muted); }}

/* ---------- Takeaway ---------- */
.ss-takeaway {{ border-top: 1px solid var(--border); padding-top: 0.8rem; margin: 0.6rem 0 0.4rem 0; }}
.ss-takeaway p {{ margin: 0; max-width: 85ch; line-height: 1.55; color: var(--text); }}
.ss-takeaway .ss-takeaway-label {{ font-size: 0.78rem; font-weight: 700; letter-spacing: 0.07em; text-transform: uppercase; color: var(--muted); margin-bottom: 0.25rem; }}

/* ---------- Definitions ---------- */
.ss-defs {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 0.4rem 1.5rem; margin: 0 0 0.8rem 0; }}
.ss-defs p {{ margin: 0; font-size: 0.9rem; color: var(--muted); line-height: 1.5; }}
.ss-defs b {{ color: var(--text); }}

/* ---------- Tables ---------- */
.ss-table {{ width: 100%; border-collapse: collapse; font-size: 0.92rem; margin: 0.25rem 0 0.75rem 0; }}
.ss-table caption {{ text-align: left; color: var(--muted); font-size: 0.85rem; padding-bottom: 0.4rem; }}
.ss-table th, .ss-table td {{ border-bottom: 1px solid var(--border); padding: 0.5rem 0.6rem; text-align: left; color: var(--text); }}
.ss-table th, .ss-table th.num {{ color: var(--muted); font-weight: 600; font-size: 0.82rem; font-family: {FONT_SANS}; }}
.ss-table tbody th {{ color: var(--text); font-weight: 500; font-size: 0.92rem; }}
.ss-table td.num, .ss-table th.num {{ text-align: right; font-family: {FONT_MONO}; }}
.ss-table-wrap {{ overflow-x: auto; }}

/* ---------- Interlock stepper ---------- */
.ss-steps {{ list-style: none; padding: 0 !important; margin: 0.4rem 0 0.9rem 0 !important; display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 0.6rem; }}
.ss-steps li {{ background: var(--surface); border: 1px solid var(--border); border-top-width: 4px; border-radius: 10px; padding: 0.7rem 0.85rem; margin: 0; }}
.ss-steps .ss-step-state {{ font-size: 0.75rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; margin: 0; color: var(--muted); }}
.ss-steps .ss-step-name {{ font-weight: 600; margin: 0.15rem 0 0.15rem 0; color: var(--text); }}
.ss-steps .ss-step-detail {{ font-size: 0.82rem; color: var(--muted); margin: 0; }}
.ss-steps li.done {{ border-top-color: var(--ok); }}
.ss-steps li.done .ss-step-state {{ color: var(--ok-text); }}
.ss-steps li.active {{ border-top-color: var(--warn); }}
.ss-steps li.active .ss-step-state {{ color: var(--warn-text); }}
.ss-steps li.alert {{ border-top-color: var(--crit); }}
.ss-steps li.alert .ss-step-state {{ color: var(--crit-text); }}
.ss-steps li.waiting {{ border-top-color: var(--border); }}

/* ---------- Streamlit widgets, so both palettes stay coherent ---------- */
.stTabs [data-baseweb="tab-list"] {{ gap: 0.25rem; border-bottom: 1px solid var(--border); }}
.stTabs [data-baseweb="tab"] {{ padding: 0.55rem 0.9rem; }}
.stTabs [data-baseweb="tab"] p {{ color: var(--muted); font-weight: 500; font-size: 0.98rem; }}
.stTabs [aria-selected="true"] p {{ color: var(--text); font-weight: 600; }}
.stTabs [data-baseweb="tab-highlight"] {{ background-color: var(--data); }}
.stTabs [data-baseweb="tab-border"] {{ background-color: var(--border); }}
[data-testid="stExpander"] {{ margin-top: 0.15rem; }}
[data-testid="stExpander"] details {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; }}
[data-testid="stExpander"] summary:hover p {{ color: var(--data); }}
.stApp [data-testid="stBaseButton-secondary"] {{ background: var(--surface); color: var(--text); border: 1px solid var(--border); }}
.stApp [data-testid="stBaseButton-secondary"]:hover {{ border-color: var(--data); color: var(--text); }}
.stApp [data-testid="stBaseButton-secondary"] p {{ color: var(--text); }}
.stApp [data-testid="stBaseButton-primary"] {{ background: var(--data); border-color: var(--data); }}
.stApp [data-testid="stBaseButton-primary"] p {{ color: {t['bg'] if t['name'] == 'dark' else '#FFFFFF'}; font-weight: 600; }}
.stApp [data-testid="stBaseButton-primary"]:disabled, .stApp [data-testid="stBaseButton-secondary"]:disabled {{ opacity: 0.55; }}
.stApp [data-testid="stBaseButton-segmented_control"], .stApp [data-testid="stBaseButton-segmented_controlActive"] {{ background: var(--surface); border-color: var(--border); }}
.stApp [data-testid="stBaseButton-segmented_control"] p {{ color: var(--muted); }}
.stApp [data-testid="stBaseButton-segmented_controlActive"] {{ background: var(--data); border-color: var(--data); }}
.stApp [data-testid="stBaseButton-segmented_controlActive"] p {{ color: {t['bg'] if t['name'] == 'dark' else '#FFFFFF'}; font-weight: 600; }}
.stApp [data-testid="stSliderTickBar"] div, .stApp [data-testid="stSliderThumbValue"] div {{ color: var(--muted); font-family: {FONT_MONO}; }}
.stApp [data-baseweb="select"] > div {{ background: var(--surface); border-color: var(--border); color: var(--text); }}
[data-baseweb="popover"] ul, [data-baseweb="popover"] li {{ background: {t['surface']}; color: {t['text']}; }}
[data-baseweb="popover"] li:hover, [data-baseweb="popover"] li[aria-selected="true"] {{ background: {t['surface_alt']}; }}
.stApp [data-testid="stCheckbox"] label span, .stApp [data-testid="stToggle"] label {{ color: var(--text); }}

/* ---------- Accessibility ---------- */
.stApp a {{ color: var(--data); }}
.stApp button:focus-visible, .stApp [role="tab"]:focus-visible, .stApp [role="slider"]:focus-visible,
.stApp [role="switch"]:focus-visible, .stApp a:focus-visible, .stApp input:focus-visible,
.stApp summary:focus-visible, .stApp [tabindex]:focus-visible {{
    outline: 3px solid var(--data) !important; outline-offset: 2px;
}}
.ss-sr-only {{ position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }}

@media (max-width: 760px) {{
    .ss-hero-single {{ grid-template-columns: 1fr; gap: 0.5rem; }}
    .ss-sequence .ss-seq-arrow {{ display: none; }}
    .ss-sequence .ss-seq-warn, .ss-sequence .ss-seq-gap, .ss-sequence .ss-seq-crit {{ flex-basis: 100%; }}
    .ss-hero-headline {{ font-size: 1.2rem; }}
    .ss-compare {{ grid-template-columns: 1fr; }}
    .ss-hero {{ grid-template-columns: 1fr; padding: 1.1rem; }}
    .ss-kpi-value {{ font-size: 2.6rem; }}
    .ss-title {{ font-size: 1.5rem; }}
}}
@media (prefers-reduced-motion: reduce) {{
    .stApp *, .stApp *::before, .stApp *::after {{ transition: none !important; animation: none !important; scroll-behavior: auto !important; }}
}}
</style>
"""


def plot_layout(t: dict, height: int, **overrides) -> dict:
    """Shared Plotly layout for palette `t`."""
    layout = dict(
        height=height,
        paper_bgcolor=t["surface"],
        plot_bgcolor=t["surface"],
        font=dict(family="IBM Plex Sans, system-ui, sans-serif", size=13, color=t["text"]),
        margin=dict(l=64, r=20, t=52, b=52),
        hoverlabel=dict(bgcolor=t["surface_alt"], bordercolor=t["border"],
                        font=dict(family="IBM Plex Mono, monospace", color=t["text"], size=12)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    font=dict(color=t["text"]), bgcolor="rgba(0,0,0,0)"),
        showlegend=False,
    )
    layout.update(overrides)
    return layout


def style_axes(fig, t: dict) -> None:
    axis = dict(automargin=True, gridcolor=t["grid"], linecolor=t["border"], zerolinecolor=t["border"],
                tickfont=dict(color=t["muted"], size=12), title_font=dict(color=t["muted"], size=12),
                showspikes=True, spikecolor=t["muted"], spikethickness=1, spikedash="dot", spikemode="across")
    fig.update_xaxes(**axis)
    fig.update_yaxes(**{k: v for k, v in axis.items() if not k.startswith("spike") and k != "showspikes"})
    # Subplot titles are paper-referenced annotations: left-align and recolour them.
    # Call this before adding any other annotations so only subplot titles are touched.
    for ann in fig.layout.annotations:
        if ann.xref == "paper" and ann.yref == "paper":
            ann.update(font=dict(size=13, color=t["text"]), x=0, xanchor="left")


PLOTLY_CONFIG = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}
