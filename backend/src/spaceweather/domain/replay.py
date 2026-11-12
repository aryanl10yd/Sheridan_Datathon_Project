from dataclasses import dataclass
from typing import Literal


WarningLevel = Literal["nominal", "watch", "warning", "critical", "unknown"]


@dataclass(frozen=True)
class ReplaySample:
    timestamp: str
    bz_gsm_nT: float | None
    sym_h_nT: float | None


def classify_geomagnetic_status(sample: ReplaySample) -> WarningLevel:
    if sample.sym_h_nT is not None and sample.sym_h_nT < -250:
        return "critical"
    if sample.bz_gsm_nT is None:
        return "unknown"
    if sample.bz_gsm_nT < -15:
        return "warning"
    if sample.bz_gsm_nT >= -15 and sample.bz_gsm_nT <= -10:
        return "watch"
    return "nominal"


classify_warning = classify_geomagnetic_status
