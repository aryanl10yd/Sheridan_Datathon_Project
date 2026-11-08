# Raspberry Pi client

The device process is intentionally separate from the backend. On a Pi Zero W
v1.1, install the pinned backend-compatible Python dependencies and run:

```bash
python device_agent.py --url http://mission-control:8000 --token "$HARDWARE_TOKEN"
```

To receive safe-mode notifications over the authenticated WebSocket:

```bash
python device_agent.py --url ws://mission-control:8000 --token "$HARDWARE_TOKEN" --listen --simulate
```

The GPIO pins use BCM numbering:

- Red LED: GPIO 17
- Yellow/amber LED: GPIO 27
- Green LED: GPIO 22
- Blue LED: GPIO 23
- Buzzer: GPIO 24

The buzzer turns on when safe mode is authorized and turns off on warning
updates, reset, and other normal hardware commands. The agent uses `gpiozero`
when available and can run in `--simulate` mode during development.

For testing without hardware, add `--simulate`. Each output update prints the
LED state and buzzer state without accessing GPIO:

```bash
python device_agent.py --url http://mission-control:8000 \
  --token "$HARDWARE_TOKEN" --sample sample.json --simulate
```
