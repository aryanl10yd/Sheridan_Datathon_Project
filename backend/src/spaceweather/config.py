from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    dataset_path: Path = Path(
        os.getenv(
            "SPACEWEATHER_DATASET",
            Path(__file__).resolve().parents[3]
            / "nasa_omni_solar_wind_storms_5min_2010-2026.csv",
        )
    )
    hardware_token: str = os.getenv("HARDWARE_TOKEN", "development-token")
    hardware_mode: str = os.getenv("HARDWARE_MODE", "physical")
    hardware_device_model: str = os.getenv("HARDWARE_DEVICE_MODEL", "Raspberry Pi Zero W v1.1")


settings = Settings()
