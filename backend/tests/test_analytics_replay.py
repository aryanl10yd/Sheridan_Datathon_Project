import pandas as pd
from fastapi.testclient import TestClient

from spaceweather.main import app
from spaceweather.domain.analytics import correlation_matrix, downsample_activity
from spaceweather.domain.replay import ReplaySample, classify_geomagnetic_status
from spaceweather.domain.replay_engine import ReplayEngine


def test_downsampling_preserves_extrema():
    frame = pd.DataFrame({
        "datetime_utc": pd.date_range("2024-01-01", periods=10, freq="5min", tz="UTC"),
        "sym_h_nT": [0, -10, -497, -20, 1, 2, -300, 3, 4, 5],
    })
    result = downsample_activity(frame, maximum_points=4)
    values = {point["sym_h_nT"] for point in result}
    assert -497 in values
    assert min(values) == -497


def test_correlation_uses_pairwise_counts_and_marks_constants():
    frame = pd.DataFrame({
        "speed_km_s": [1, 2, None, 4],
        "pressure_nPa": [1, 2, 3, 4],
        "bz_gsm_nT": [5, 5, 5, 5],
        "ae_nT": [1, None, 3, 4],
    })
    result = correlation_matrix(frame)
    assert result["valid_observations"][0][1] == 3
    assert result["coefficients"][0][2] is None


def test_status_boundaries_and_critical_precedence():
    assert classify_geomagnetic_status(ReplaySample("t", -10, 0)) == "watch"
    assert classify_geomagnetic_status(ReplaySample("t", -15, 0)) == "watch"
    assert classify_geomagnetic_status(ReplaySample("t", -15.1, 0)) == "warning"
    assert classify_geomagnetic_status(ReplaySample("t", -5, -250.1)) == "critical"
    assert classify_geomagnetic_status(ReplaySample("t", None, None)) == "unknown"


def test_replay_bounds_and_reset():
    engine = ReplayEngine([ReplaySample(str(i), float(i), 0) for i in range(3)])
    assert engine.current.timestamp == "0"
    engine.step()
    engine.seek(999)
    assert engine.complete and not engine.playing
    engine.reset()
    assert engine.index == 0 and not engine.playing


def test_hardware_status_requires_authentication_and_reports_disconnected_device():
    client = TestClient(app)
    assert client.get("/api/hardware/status").status_code == 401
    response = client.get("/api/hardware/status", headers={"X-Hardware-Token": "development-token"})
    assert response.status_code == 200
    assert response.json()["simulated"] is False
    assert response.json()["connection"] == "disconnected"
    command = client.post("/api/hardware/self_test", headers={"X-Hardware-Token": "development-token"})
    assert command.status_code == 503


def test_safe_mode_requires_connected_hardware():
    client = TestClient(app)
    response = client.post(
        "/api/safe-mode/authorize",
        headers={"X-Hardware-Token": "development-token"},
        json={"action": "grid_transformer_decoupling", "replay_index": 0},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Hardware device is disconnected"
