from dataclasses import dataclass

from .replay import ReplaySample, classify_geomagnetic_status


@dataclass
class ReplayEngine:
    observations: list[ReplaySample]
    index: int = 0
    playing: bool = False
    speed: int = 1

    def __post_init__(self) -> None:
        if not self.observations:
            raise ValueError("Replay requires at least one observation")

    @property
    def current(self) -> ReplaySample:
        return self.observations[self.index]

    @property
    def complete(self) -> bool:
        return self.index == len(self.observations) - 1

    def state(self) -> dict:
        return {
            "index": self.index,
            "total": len(self.observations),
            "progress": self.index / (len(self.observations) - 1) if len(self.observations) > 1 else 1,
            "playing": self.playing,
            "speed": self.speed,
            "complete": self.complete,
            "observation": self.current.__dict__,
            "status": classify_geomagnetic_status(self.current),
        }

    def play(self) -> dict:
        if not self.complete:
            self.playing = True
        return self.state()

    def pause(self) -> dict:
        self.playing = False
        return self.state()

    def reset(self) -> dict:
        self.index, self.playing = 0, False
        return self.state()

    def seek(self, index: int) -> dict:
        self.index = max(0, min(index, len(self.observations) - 1))
        if self.complete:
            self.playing = False
        return self.state()

    def step(self) -> dict:
        if self.index < len(self.observations) - 1:
            self.index += 1
        else:
            self.playing = False
        return self.state()
