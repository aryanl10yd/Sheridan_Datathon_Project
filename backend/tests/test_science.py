from datetime import datetime, timezone
import pandas as pd

from spaceweather.domain.science import investigate


def test_missing_values_break_sustained_threshold():
    frame = pd.DataFrame({
        "datetime_utc": pd.date_range("2024-05-10", periods=6, freq="5min", tz="UTC"),
        "bz_gsm_nT": [-12, -12, None, -12, -12, -12],
        "sym_h_nT": [0, 0, 0, -110, -110, -110],
    })
    result = investigate(frame)
    assert result["bz_onset"] == "2024-05-10T00:15:00+00:00"
    assert result["sym_h_onset"] == "2024-05-10T00:15:00+00:00"
    assert result["lead_minutes"] == 0


def test_no_disturbance_returns_no_lead():
    frame = pd.DataFrame({
        "datetime_utc": pd.date_range("2024-05-10", periods=4, freq="5min", tz="UTC"),
        "bz_gsm_nT": [-12, -12, -12, -12],
        "sym_h_nT": [0, 0, 0, 0],
    })
    assert investigate(frame)["sym_h_onset"] is None
