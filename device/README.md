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

The default GPIO pins are BCM 17 (green), 27 (amber), and 22 (red). The agent
uses `gpiozero` when available and can run in `--simulate` mode during
development.
