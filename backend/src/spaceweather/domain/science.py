from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd


@dataclass(frozen=True)
class Thresholds:
    bz_southward_nT: float = -10.0
    sym_h_disturbance_nT: float = -100.0
    sustained_intervals: int = 3
    max_lead_hours: float = 6.0


@dataclass(frozen=True)
class LeadEvent:
    bz_onset: datetime
    sym_h_onset: Optional[datetime]
    lead_minutes: Optional[float]
    bz_min_nT: float
    sym_h_min_nT: float


REQUIRED_COLUMNS = ("datetime_utc", "bz_gsm_nT", "sym_h_nT")


def load_observations(dataset_path: Path, start: datetime, end: datetime) -> pd.DataFrame:
    """Load a bounded, typed interval without filling missing observations."""
    if not dataset_path.is_file():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")
    frame = pd.read_csv(dataset_path, usecols=list(REQUIRED_COLUMNS))
    missing = set(REQUIRED_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"Dataset is missing required columns: {sorted(missing)}")
    frame["datetime_utc"] = pd.to_datetime(frame["datetime_utc"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["datetime_utc"])
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    if start_ts.tzinfo is None:
        start_ts = start_ts.tz_localize("UTC")
    else:
        start_ts = start_ts.tz_convert("UTC")
    if end_ts.tzinfo is None:
        end_ts = end_ts.tz_localize("UTC")
    else:
        end_ts = end_ts.tz_convert("UTC")
    return (
        frame.loc[
            (frame["datetime_utc"] >= start_ts)
            & (frame["datetime_utc"] < end_ts)
        ]
        .sort_values("datetime_utc")
        .reset_index(drop=True)
    )


def _first_sustained_time(
    frame: pd.DataFrame, column: str, threshold: float, intervals: int
) -> Optional[pd.Timestamp]:
    valid = frame[column].notna() & (frame[column] <= threshold)
    # A missing sample breaks a sustained interval; rolling over the boolean
    # mask therefore never treats missing data as a threshold crossing.
    sustained = valid.rolling(intervals, min_periods=intervals).sum().eq(intervals)
    positions = sustained[sustained].index
    return frame.loc[positions[0] - intervals + 1, "datetime_utc"] if len(positions) else None


def investigate(frame: pd.DataFrame, thresholds: Thresholds = Thresholds()) -> dict:
    """Measure whether sustained southward Bz precedes SYM-H disturbance."""
    if frame.empty:
        return {"observations": 0, "bz_onset": None, "sym_h_onset": None, "lead_minutes": None}
    bz_onset = _first_sustained_time(
        frame, "bz_gsm_nT", thresholds.bz_southward_nT, thresholds.sustained_intervals
    )
    sym_onset = _first_sustained_time(
        frame, "sym_h_nT", thresholds.sym_h_disturbance_nT, thresholds.sustained_intervals
    )
    lead = None
    if bz_onset is not None and sym_onset is not None:
        minutes = (sym_onset - bz_onset).total_seconds() / 60
        if 0 <= minutes <= thresholds.max_lead_hours * 60:
            lead = minutes
    return {
        "observations": int(len(frame)),
        "missing_bz": int(frame["bz_gsm_nT"].isna().sum()),
        "missing_sym_h": int(frame["sym_h_nT"].isna().sum()),
        "bz_onset": bz_onset.isoformat() if bz_onset is not None else None,
        "sym_h_onset": sym_onset.isoformat() if sym_onset is not None else None,
        "lead_minutes": lead,
        "bz_min_nT": float(frame["bz_gsm_nT"].min()) if frame["bz_gsm_nT"].notna().any() else None,
        "sym_h_min_nT": float(frame["sym_h_nT"].min()) if frame["sym_h_nT"].notna().any() else None,
        "thresholds": {
            "bz_southward_nT": thresholds.bz_southward_nT,
            "sym_h_disturbance_nT": thresholds.sym_h_disturbance_nT,
            "sustained_intervals": thresholds.sustained_intervals,
        },
    }


def serialize_observations(frame: pd.DataFrame) -> list[dict]:
    return [
        {
            "timestamp": row.datetime_utc.isoformat(),
            "bz_gsm_nT": None if pd.isna(row.bz_gsm_nT) else float(row.bz_gsm_nT),
            "sym_h_nT": None if pd.isna(row.sym_h_nT) else float(row.sym_h_nT),
        }
        for row in frame.itertuples(index=False)
    ]
