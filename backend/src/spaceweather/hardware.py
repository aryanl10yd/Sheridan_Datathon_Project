from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LedState:
    green: bool
    amber: bool
    red: bool
    blue: bool = False


class Hardware(Protocol):
    def set_warning(self, level: str) -> LedState: ...
    def reset(self) -> LedState:
        ...
    def authorize(self) -> LedState:  ...


class SimulatedHardware:
    def __init__(self) -> None:
        self.state = LedState(True, False, False)

    def set_warning(self, level: str) -> LedState:
        self.state = LedState(level == "nominal", level == "watch", level in {"warning", "critical"})
        return self.state

    def reset(self) -> LedState:
        return self.set_warning("normal")

    def authorize(self) -> LedState:
        self.state = LedState(self.state.green, self.state.amber, self.state.red, True)
        return self.state


class DisconnectedHardware:
    """Backend placeholder until the authenticated Raspberry Pi connects."""

    def __init__(self) -> None:
        self.state = LedState(False, False, False, False)

    def set_warning(self, level: str) -> LedState:
        return self.state

    def reset(self) -> LedState:
        return self.state

    def authorize(self) -> LedState:
        return self.state


class GpioZeroHardware:
    def __init__(self, green_pin: int = 17, amber_pin: int = 27, red_pin: int = 22) -> None:
        from gpiozero import LED
        self.green, self.amber, self.red = LED(green_pin), LED(amber_pin), LED(red_pin)
        self.blue = LED(23)
        self.state = LedState(True, False, False)

    def set_warning(self, level: str) -> LedState:
        state = SimulatedHardware().set_warning(level)
        for led, enabled in ((self.green, state.green), (self.amber, state.amber), (self.red, state.red), (self.blue, state.blue)):
            led.on() if enabled else led.off()
        self.state = state
        return state

    def reset(self) -> LedState:
        return self.set_warning("normal")

    def authorize(self) -> LedState:
        self.blue.on()
        self.state = LedState(self.state.green, self.state.amber, self.state.red, True)
        return self.state
