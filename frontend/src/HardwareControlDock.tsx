import { useEffect, useState } from "react";

type LedState = { green: boolean; amber: boolean; red: boolean; blue: boolean };
type HardwareStatus = {
  device_id: string | null;
  model: string;
  connection: "connected" | "disconnected" | "stale" | "simulated";
  simulated: boolean;
  mode: string;
  last_heartbeat: string | null;
  leds: LedState;
  safe_mode: "idle" | "acknowledged";
  latest_error: string | null;
};
type HardwareEvent = { event_id: string; timestamp: string; action: string; status: string };

const hardwareToken = import.meta.env.VITE_HARDWARE_TOKEN ?? "development-token";

async function hardwareApi<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: { "X-Hardware-Token": hardwareToken, ...options?.headers },
  });
  if (!response.ok) {
    const body = await response.text();
    try {
      const parsed = JSON.parse(body) as { detail?: string };
      throw new Error(parsed.detail ?? body);
    } catch (error) {
      if (error instanceof SyntaxError) throw new Error(body);
      throw error;
    }
  }
  return response.json();
}

function formatHeartbeat(value: string | null) {
  return value ? new Date(value).toLocaleString() : "No heartbeat";
}

export function HardwareControlDock() {
  const [expanded, setExpanded] = useState(false);
  const [status, setStatus] = useState<HardwareStatus>();
  const [events, setEvents] = useState<HardwareEvent[]>([]);
  const [loadingCommand, setLoadingCommand] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refresh = async () => {
    try {
      const [nextStatus, eventResponse] = await Promise.all([
        hardwareApi<HardwareStatus>("/api/hardware/status"),
        hardwareApi<{ events: HardwareEvent[] }>("/api/events"),
      ]);
      setStatus(nextStatus);
      setEvents(eventResponse.events.slice(-8).reverse());
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => window.clearInterval(timer);
  }, []);

  const runCommand = async (command: "self_test" | "synchronize" | "reset") => {
    if (loadingCommand) return;
    setLoadingCommand(command);
    setError("");
    setNotice("");
    try {
      const result = await hardwareApi<{ status: string; hardware: HardwareStatus }>(`/api/hardware/${command}`, { method: "POST" });
      setStatus(result.hardware);
      setNotice(result.status === "pending" ? "Command sent; waiting for device acknowledgement." : "Command completed.");
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoadingCommand("");
    }
  };

  const connectionLabel = status?.connection.toUpperCase() ?? "CONNECTING";
  const ledRows = [
    ["green", "NOMINAL"],
    ["amber", "WATCH / WARNING"],
    ["red", "CRITICAL"],
    ["blue", "SAFE MODE ACKNOWLEDGED"],
  ] as const;

  return (
    <aside className={`hardware-dock ${expanded ? "expanded" : "collapsed"}`} aria-label="Raspberry Pi hardware control">
      <button className="hardware-dock-header" aria-expanded={expanded} aria-controls="hardware-dock-panel" onClick={() => setExpanded(value => !value)}>
        <span><strong>Raspberry Pi · {status?.device_id ?? "Not connected"}</strong><span className={`connection ${status?.connection ?? "stale"}`}>{connectionLabel}</span></span>
        <span className="heartbeat">Heartbeat: {formatHeartbeat(status?.last_heartbeat ?? null)}</span>
        <span className="dock-toggle" aria-hidden="true">{expanded ? "⌄" : "⌃"}</span>
      </button>
      {expanded && <div id="hardware-dock-panel" className="hardware-dock-panel">
        {!status && !error && <p className="dock-muted">Connecting to hardware service…</p>}
        {error && <p className="dock-error" role="alert">{error}</p>}
        {status && <div className="hardware-grid">
          <section>
            <h3>Device information</h3>
            <dl className="device-details">
              <div><dt>Device ID</dt><dd>{status.device_id}</dd></div>
              <div><dt>Model</dt><dd>{status.model}</dd></div>
              <div><dt>Connection</dt><dd>{connectionLabel}</dd></div>
              <div><dt>Mode</dt><dd>{status.mode}</dd></div>
              <div><dt>Latest error</dt><dd>{status.latest_error ?? "None"}</dd></div>
            </dl>
          </section>
          <section>
            <h3>Physical LED monitoring</h3>
            <ul className="led-list">{ledRows.map(([color, label]) => <li key={color}><span className={`led-dot ${color} ${status.leds[color] ? "on" : ""}`} />{label}<strong>{status.leds[color] ? "ON" : "OFF"}</strong></li>)}</ul>
          </section>
          <section>
            <h3>Hardware controls</h3>
            <div className="dock-controls">
              <button onClick={() => runCommand("self_test")} disabled={Boolean(loadingCommand)}> {loadingCommand === "self_test" ? "RUNNING…" : "RUN LED SELF-TEST"} </button>
              <button onClick={() => runCommand("synchronize")} disabled={Boolean(loadingCommand)}> {loadingCommand === "synchronize" ? "SYNCHRONIZING…" : "SYNCHRONIZE DEVICE"} </button>
              <button onClick={() => runCommand("reset")} disabled={Boolean(loadingCommand)}> {loadingCommand === "reset" ? "RESETTING…" : "RESET INDICATORS"} </button>
            </div>
            {notice && <p className="dock-success" role="status">{notice}</p>}
          </section>
          <section>
            <h3>Safe Mode</h3>
            <p className="safe-mode-status"><span className={`safe-mode-dot ${status.safe_mode}`} />SAFE MODE REQUEST: <strong>{status.safe_mode.toUpperCase()}</strong></p>
            <p className="dock-muted">{status.safe_mode === "acknowledged" ? "Physical acknowledgement received." : "No pending physical confirmation."}</p>
          </section>
          <section className="dock-events">
            <h3>Hardware event log</h3>
            {events.length ? events.map(event => <div key={event.event_id}>{event.timestamp} · {event.action} · {event.status}</div>) : <p className="dock-muted">No hardware events.</p>}
          </section>
        </div>}
      </div>}
    </aside>
  );
}
