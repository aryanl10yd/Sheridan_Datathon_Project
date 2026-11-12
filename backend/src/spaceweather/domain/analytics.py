from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


ANALYTICS_COLUMNS = (
    "datetime_utc",
    "sym_h_nT",
    "speed_km_s",
    "pressure_nPa",
    "bz_gsm_nT",
    "ae_nT",
)


@dataclass(frozen=True)
class Period:
    start: datetime | None = None
    end: datetime | None = None


def load_analytics_data(path: Path, period: Period = Period()) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Dataset not found: {path}")
    frame = pd.read_csv(path, usecols=list(ANALYTICS_COLUMNS))
    frame["datetime_utc"] = pd.to_datetime(frame["datetime_utc"], utc=True, errors="coerce")
    for column in ANALYTICS_COLUMNS[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["datetime_utc"]).sort_values("datetime_utc")
    if period.start is not None:
        start = pd.Timestamp(period.start)
        frame = frame[frame["datetime_utc"] >= (start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC"))]
    if period.end is not None:
        end = pd.Timestamp(period.end)
        frame = frame[frame["datetime_utc"] < (end.tz_localize("UTC") if end.tzinfo is None else end.tz_convert("UTC"))]
    return frame.reset_index(drop=True)


def _iso(value: pd.Timestamp) -> str:
    return value.isoformat()


def downsample_activity(frame: pd.DataFrame, maximum_points: int = 2000) -> list[dict]:
    """Bucket SYM-H while retaining each bucket's observed extrema."""
    valid = frame.dropna(subset=["sym_h_nT"]).copy()
    if valid.empty:
        return []
    if len(valid) <= maximum_points:
        selected = valid
    else:
        bucket_count = max(1, maximum_points // 2)
        buckets = pd.cut(valid.index, bins=bucket_count, labels=False)
        rows: list[pd.Series] = []
        for _, bucket in valid.groupby(buckets, observed=True):
            rows.extend([bucket.loc[bucket["sym_h_nT"].idxmax()], bucket.loc[bucket["sym_h_nT"].idxmin()]])
        selected = pd.DataFrame(rows).drop_duplicates(subset=["datetime_utc"]).sort_values("datetime_utc")
    return [{"timestamp": _iso(row.datetime_utc), "sym_h_nT": float(row.sym_h_nT)} for row in selected.itertuples()]


def activity_summary(frame: pd.DataFrame) -> dict:
    valid = frame.dropna(subset=["sym_h_nT"])
    minimum = valid.loc[valid["sym_h_nT"].idxmin()] if not valid.empty else None
    return {
        "coverage_start": _iso(frame["datetime_utc"].min()) if not frame.empty else None,
        "coverage_end": _iso(frame["datetime_utc"].max()) if not frame.empty else None,
        "observations": int(len(frame)),
        "minimum_sym_h_nT": float(minimum.sym_h_nT) if minimum is not None else None,
        "minimum_timestamp": _iso(minimum.datetime_utc) if minimum is not None else None,
        "series": downsample_activity(frame),
    }


CORRELATION_VARIABLES = (
    ("speed_km_s", "Solar wind speed", "km/s"),
    ("pressure_nPa", "Dynamic pressure", "nPa"),
    ("bz_gsm_nT", "IMF Bz GSM", "nT"),
    ("ae_nT", "Auroral electrojet", "nT"),
)


def correlation_matrix(frame: pd.DataFrame) -> dict:
    values = frame[[column for column, _, _ in CORRELATION_VARIABLES]]
    arrays = {column: values[column].to_numpy(dtype=float) for column, _, _ in CORRELATION_VARIABLES}
    matrix: list[list[float | None]] = []
    counts: list[list[int]] = []
    for left in values:
        row: list[float | None] = []
        count_row: list[int] = []
        for right in values:
            mask = np.isfinite(arrays[left]) & np.isfinite(arrays[right])
            left_values, right_values = arrays[left][mask], arrays[right][mask]
            count_row.append(int(mask.sum()))
            if len(left_values) < 2 or np.ptp(left_values) == 0 or np.ptp(right_values) == 0:
                row.append(None)
            else:
                row.append(float(np.corrcoef(left_values, right_values)[0, 1]))
        matrix.append(row)
        counts.append(count_row)
    return {
        "variables": [{"column": column, "label": label, "unit": unit} for column, label, unit in CORRELATION_VARIABLES],
        "coefficients": matrix,
        "valid_observations": counts,
        "explanation": "Pearson correlation describes association in pairwise complete observations; it does not establish causation.",
    }
