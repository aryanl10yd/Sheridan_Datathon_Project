"""Small authenticated Raspberry Pi hardware client."""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen


def send_warning(url: str, token: str, sample: dict) -> dict:
    payload = json.dumps(sample).encode("utf-8")
    request = Request(
        f"{url.rstrip('/')}/api/replay/classify",
        data=payload,
        headers={"Content-Type": "application/json", "X-Hardware-Token": token},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.load(response)


GPIO_PINS = {
    "red": 17,
    "amber": 27,
    "green": 22,
    "blue": 23,
    "buzzer": 24,
}


def apply_outputs(leds: dict, buzzer_on: bool, simulate: bool) -> None:
    if simulate:
        print(json.dumps({"simulated": True, "leds": leds, "buzzer": buzzer_on}))
        return
    from gpiozero import Buzzer, LED

    leds_by_pin = {
        name: LED(pin)
        for name, pin in GPIO_PINS.items()
        if name != "buzzer"
    }
    for name, led in leds_by_pin.items():
        led.on() if leds.get(name, False) else led.off()
    buzzer = Buzzer(GPIO_PINS["buzzer"])
    buzzer.on() if buzzer_on else buzzer.off()


def warning_leds(level: str) -> dict:
    return {
        "green": level == "nominal",
        "amber": level == "watch",
        "red": level in {"warning", "critical"},
        "blue": False,
    }


def listen_for_authorization(ws_url: str, token: str, simulate: bool) -> None:
    import websocket

    socket = websocket.create_connection(f"{ws_url}?token={token}", timeout=30)
    try:
        last_heartbeat = 0.0
        while True:
            socket.settimeout(5)
            if time.monotonic() - last_heartbeat >= 5:
                socket.send(json.dumps({
                    "type": "heartbeat",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "device_id": device_id(),
                    "model": device_model(),
                }))
                last_heartbeat = time.monotonic()
            try:
                message = json.loads(socket.recv())
            except websocket.WebSocketTimeoutException:
                continue
            if message.get("type") == "safe_mode_authorized":
                apply_outputs(message["leds"], buzzer_on=True, simulate=simulate)
                socket.send(json.dumps({"type": "ack", "command": "safe_mode", "status": "acknowledged", "leds": message["leds"]}))
            elif message.get("type") == "warning_update":
                leds = warning_leds(message["level"])
                apply_outputs(leds, buzzer_on=False, simulate=simulate)
                socket.send(json.dumps({"type": "ack", "command": "warning_update", "status": "acknowledged", "leds": leds}))
            elif message.get("type") == "hardware_command":
                if message["command"] == "reset":
                    leds = {"green": True, "amber": False, "red": False, "blue": False}
                else:
                    leds = {"green": True, "amber": False, "red": False, "blue": False}
                apply_outputs(leds, buzzer_on=False, simulate=simulate)
                socket.send(json.dumps({"type": "ack", "command": message["command"], "status": "acknowledged", "leds": leds}))
    finally:
        socket.close()


def device_id() -> str:
    return os.uname().nodename


def device_model() -> str:
    try:
        with open("/proc/device-tree/model", encoding="utf-8") as file:
            return file.read().rstrip("\x00\n")
    except (FileNotFoundError, OSError):
        return "Raspberry Pi"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--sample", help="JSON file containing one replay sample")
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--listen", action="store_true", help="Listen for safe-mode events")
    args = parser.parse_args()
    if args.listen:
        listen_for_authorization(args.url.rstrip("/") + "/api/hardware/ws", args.token, args.simulate)
    else:
        if not args.sample:
            parser.error("--sample is required unless --listen is used")
        with open(args.sample, encoding="utf-8") as file:
            result = send_warning(args.url, args.token, json.load(file))
        apply_outputs(result["leds"], buzzer_on=False, simulate=args.simulate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
