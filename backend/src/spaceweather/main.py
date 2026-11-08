from datetime import datetime, timezone
from uuid import uuid4
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .config import settings
from .domain.analytics import Period, activity_summary, correlation_matrix, load_analytics_data
from .domain.replay import ReplaySample, classify_geomagnetic_status
from .domain.replay_engine import ReplayEngine
from .domain.science import investigate, load_observations, serialize_observations
from .hardware import DisconnectedHardware, SimulatedHardware

app = FastAPI(title="Vexcel Mission Control", version="1.0.0")
hardware = SimulatedHardware() if settings.hardware_mode == "simulated" else DisconnectedHardware()
connected_devices: set[WebSocket] = set()
event_log: list[dict] = []
last_heartbeat_at: datetime | None = None
last_reported_leds = hardware.state.__dict__.copy()
last_hardware_error: str | None = None
connected_device_id: str | None = None
connected_device_model: str | None = None
COMMANDS = {"self_test", "synchronize", "reset"}


def storm_window():
    return load_observations(
        settings.dataset_path,
        datetime(2024, 5, 10, tzinfo=timezone.utc),
        datetime(2024, 5, 12, tzinfo=timezone.utc),
    )


def build_replay() -> ReplayEngine:
    frame = storm_window()
    return ReplayEngine([
        ReplaySample(
            timestamp=row.datetime_utc.isoformat(),
            bz_gsm_nT=None if row.bz_gsm_nT != row.bz_gsm_nT else float(row.bz_gsm_nT),
            sym_h_nT=None if row.sym_h_nT != row.sym_h_nT else float(row.sym_h_nT),
        )
        for row in frame.itertuples(index=False)
    ])


replay = build_replay()


class ReplayRequest(BaseModel):
    timestamp: str
    bz_gsm_nT: float | None = None
    sym_h_nT: float | None = None


@app.get("/api/health")
def health():
    return {"status": "ok", "dataset": str(settings.dataset_path)}


@app.get("/api/investigation")
def investigation():
    frame = storm_window()
    result = investigate(frame)
    result["series"] = serialize_observations(frame)
    return result


@app.get("/api/historical-activity")
def historical_activity():
    return activity_summary(load_analytics_data(settings.dataset_path))


@app.get("/api/correlations")
def correlations(period: str = "all"):
    selected = (
        Period(datetime(2024, 5, 10, tzinfo=timezone.utc), datetime(2024, 5, 12, tzinfo=timezone.utc))
        if period == "storm"
        else Period()
    )
    return correlation_matrix(load_analytics_data(settings.dataset_path, selected))


@app.get("/api/replay/state")
def replay_state():
    return replay.state()


@app.post("/api/replay/{action}")
async def replay_control(action: str, index: int | None = None, speed: int | None = None):
    if speed is not None:
        if speed not in {1, 2, 5, 10}:
            raise HTTPException(status_code=400, detail="Speed must be 1, 2, 5, or 10")
        replay.speed = speed
    if action == "speed":
        state = replay.state()
        await publish_replay_warning(state)
        return state
    if action == "play":
        state = replay.play()
        await publish_replay_warning(state)
        return state
    if action == "pause":
        state = replay.pause()
        await publish_replay_warning(state)
        return state
    if action == "reset":
        state = replay.reset()
        await publish_replay_warning(state)
        return state
    if action == "step":
        state = replay.step()
        await publish_replay_warning(state)
        return state
    if action == "seek" and index is not None:
        state = replay.seek(index)
        await publish_replay_warning(state)
        return state
    raise HTTPException(status_code=400, detail="Invalid replay action")


@app.post("/api/replay/classify")
async def replay_classify(request: ReplayRequest, x_hardware_token: str | None = Header(default=None)):
    if x_hardware_token != settings.hardware_token:
        raise HTTPException(status_code=401, detail="Invalid hardware token")
    level = classify_geomagnetic_status(ReplaySample(**request.model_dump()))
    state = hardware.set_warning(level)
    await publish_warning(level, state.__dict__)
    return {"level": level, "leds": state.__dict__}


class AuthorizationRequest(BaseModel):
    action: str
    replay_index: int


@app.get("/api/events")
def events():
    return {"events": event_log}


def require_hardware_token(token: str | None) -> None:
    if token != settings.hardware_token:
        raise HTTPException(status_code=401, detail="Invalid hardware token")


def hardware_status() -> dict:
    global last_hardware_error
    if settings.hardware_mode == "simulated":
        connection = "simulated"
        heartbeat = datetime.now(timezone.utc)
        leds = hardware.state.__dict__
    elif not connected_devices:
        connection = "disconnected"
        heartbeat = last_heartbeat_at
        leds = last_reported_leds
    elif last_heartbeat_at and (datetime.now(timezone.utc) - last_heartbeat_at).total_seconds() > 30:
        connection = "stale"
        heartbeat = last_heartbeat_at
        leds = last_reported_leds
    else:
        connection = "connected"
        heartbeat = last_heartbeat_at
        leds = last_reported_leds
    return {
        "device_id": connected_device_id if connection in {"connected", "stale"} else None,
        "model": connected_device_model if connection in {"connected", "stale"} else settings.hardware_device_model,
        "connection": connection,
        "simulated": settings.hardware_mode == "simulated",
        "mode": "SIMULATED DEVICE" if settings.hardware_mode == "simulated" else "PHYSICAL DEVICE",
        "last_heartbeat": heartbeat.isoformat() if heartbeat else None,
        "leds": leds,
        "safe_mode": "acknowledged" if leds.get("blue") else "idle",
        "latest_error": last_hardware_error,
    }


async def publish_warning(level: str, leds: dict[str, bool]) -> None:
    if not connected_devices:
        return
    message = {"type": "warning_update", "level": level, "leds": leds}
    disconnected: set[WebSocket] = set()
    for device in connected_devices:
        try:
            await device.send_json(message)
        except (RuntimeError, WebSocketDisconnect) as error:
            disconnected.add(device)
            global last_hardware_error
            last_hardware_error = str(error)
    connected_devices.difference_update(disconnected)


async def publish_replay_warning(state: dict) -> None:
    sample = ReplaySample(**state["observation"])
    leds = hardware.set_warning(state["status"]).__dict__
    await publish_warning(classify_geomagnetic_status(sample), leds)


@app.get("/api/hardware/status")
def hardware_status_endpoint(x_hardware_token: str | None = Header(default=None)):
    require_hardware_token(x_hardware_token)
    return hardware_status()


async def send_hardware_command(command: str) -> dict:
    global last_hardware_error, last_reported_leds
    if settings.hardware_mode == "simulated":
        if command == "reset":
            last_reported_leds = hardware.reset().__dict__
        else:
            last_reported_leds = hardware.state.__dict__
        return {"command": command, "status": "succeeded", "hardware": hardware_status()}
    if not connected_devices:
        raise HTTPException(status_code=503, detail="Hardware device is disconnected")
    message = {"type": "hardware_command", "command": command, "command_id": str(uuid4())}
    disconnected: set[WebSocket] = set()
    for device in connected_devices:
        try:
            await device.send_json(message)
        except (RuntimeError, WebSocketDisconnect) as error:
            last_hardware_error = str(error)
            disconnected.add(device)
    connected_devices.difference_update(disconnected)
    if disconnected and not connected_devices:
        raise HTTPException(status_code=503, detail="Hardware device disconnected while sending command")
    event_log.append({"event_id": str(uuid4()), "timestamp": datetime.now(timezone.utc).isoformat(), "action": command, "status": "sent"})
    return {"command": command, "status": "pending", "hardware": hardware_status()}


@app.post("/api/hardware/{command}")
async def hardware_command(command: str, x_hardware_token: str | None = Header(default=None)):
    require_hardware_token(x_hardware_token)
    if command not in COMMANDS:
        raise HTTPException(status_code=404, detail="Unknown hardware command")
    return await send_hardware_command(command)


@app.post("/api/safe-mode/authorize")
async def authorize_safe_mode(
    request: AuthorizationRequest,
    x_hardware_token: str | None = Header(default=None),
):
    require_hardware_token(x_hardware_token)
    if not connected_devices:
        raise HTTPException(status_code=503, detail="Hardware device is disconnected")
    if request.action not in {"grid_transformer_decoupling", "satellite_safe_orientation"}:
        raise HTTPException(status_code=400, detail="Unknown simulation action")
    if any(event["action"] == request.action and event["replay_index"] == request.replay_index for event in event_log):
        raise HTTPException(status_code=409, detail="Authorization already recorded")
    event = {
        "event_id": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": request.action,
        "replay_index": request.replay_index,
        "replay_state": replay.state(),
        "simulation_only": True,
    }
    event_log.append(event)
    leds = hardware.authorize()
    message = {"type": "safe_mode_authorized", "event": event, "leds": leds.__dict__}
    disconnected: set[WebSocket] = set()
    for device in connected_devices:
        try:
            await device.send_json(message)
        except Exception:
            disconnected.add(device)
    connected_devices.difference_update(disconnected)
    return message


@app.websocket("/api/hardware/ws")
async def hardware_websocket(websocket: WebSocket):
    global last_heartbeat_at, last_reported_leds, last_hardware_error, connected_device_id, connected_device_model
    if websocket.query_params.get("token") != settings.hardware_token:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    connected_devices.add(websocket)
    last_heartbeat_at = datetime.now(timezone.utc)
    try:
        while True:
            message = await websocket.receive_json()
            last_heartbeat_at = datetime.now(timezone.utc)
            if message.get("type") == "heartbeat":
                if isinstance(message.get("device_id"), str) and message["device_id"].strip():
                    connected_device_id = message["device_id"].strip()
                if isinstance(message.get("model"), str) and message["model"].strip():
                    connected_device_model = message["model"].strip()
                if isinstance(message.get("leds"), dict):
                    last_reported_leds = message["leds"]
            elif message.get("type") == "ack":
                event_log.append({
                    "event_id": str(uuid4()),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "action": message.get("command", "hardware command"),
                    "status": message.get("status", "acknowledged"),
                })
                if isinstance(message.get("leds"), dict):
                    last_reported_leds = message["leds"]
    except WebSocketDisconnect:
        connected_devices.discard(websocket)
        if not connected_devices:
            connected_device_id = None
            connected_device_model = None
    except (RuntimeError, ValueError, TypeError) as error:
        last_hardware_error = str(error)
        connected_devices.discard(websocket)
        if not connected_devices:
            connected_device_id = None
            connected_device_model = None
