import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import Plot from "react-plotly.js";
import { HardwareControlDock } from "./HardwareControlDock";
import { PrimaryNavigation } from "./PrimaryNavigation";
import "./styles.css";

type Observation = { timestamp: string; bz_gsm_nT: number | null; sym_h_nT: number | null };
type ReplayState = { index: number; total: number; progress: number; playing: boolean; speed: number; complete: boolean; observation: Observation; status: string };
type Activity = { coverage_start: string | null; coverage_end: string | null; observations: number; minimum_sym_h_nT: number | null; minimum_timestamp: string | null; series: { timestamp: string; sym_h_nT: number }[] };
type Correlations = { variables: { column: string; label: string; unit: string }[]; coefficients: (number | null)[][]; valid_observations: number[][]; explanation: string };

const api = async <T,>(path: string, options?: RequestInit): Promise<T> => {
  const response = await fetch(path, options);
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
};

function statusLabel(status: string) {
  return status === "critical" ? "CRITICAL G5 SUPERSTORM" : status.toUpperCase();
}

function Chart({ data, layout }: { data: any[]; layout: any }) {
  return <Plot data={data} layout={{ ...layout, autosize: true, paper_bgcolor: "#15191d", plot_bgcolor: "#15191d", font: { color: "#f8f8f5" }, margin: { l: 54, r: 18, t: 12, b: 48 }, xaxis: { gridcolor: "#384047" }, yaxis: { gridcolor: "#384047" } }} useResizeHandler style={{ width: "100%", height: `${layout.height}px`, display: "block" }} config={{ responsive: true, displaylogo: false }} />;
}

function App() {
  const [activity, setActivity] = useState<Activity>();
  const [investigation, setInvestigation] = useState<any>();
  const [correlations, setCorrelations] = useState<Correlations>();
  const [correlationPeriod, setCorrelationPeriod] = useState("all");
  const [replay, setReplay] = useState<ReplayState>();
  const [selectedAction, setSelectedAction] = useState("");
  const [events, setEvents] = useState<any[]>([]);
  const [error, setError] = useState("");
  const [activeSection, setActiveSection] = useState("historical");

  const refreshReplay = () => api<ReplayState>("/api/replay/state").then(setReplay).catch(e => setError(String(e)));
  useEffect(() => {
    Promise.all([api<Activity>("/api/historical-activity"), api<any>("/api/investigation"), api<Correlations>("/api/correlations"), api<any>("/api/events")])
      .then(([historical, storm, matrix, log]) => { setActivity(historical); setInvestigation(storm); setCorrelations(matrix); setEvents(log.events); })
      .catch(e => setError(String(e)));
    refreshReplay();
  }, []);
  useEffect(() => {
    if (!replay?.playing) return;
    const timer = window.setInterval(() => api<ReplayState>("/api/replay/step", { method: "POST" }).then(setReplay).catch(e => setError(String(e))), 1000 / replay.speed);
    return () => window.clearInterval(timer);
  }, [replay?.playing, replay?.speed]);
  useEffect(() => { api<Correlations>(`/api/correlations?period=${correlationPeriod}`).then(setCorrelations).catch(e => setError(String(e))); }, [correlationPeriod]);

  const control = (action: string, query = "") => api<ReplayState>(`/api/replay/${action}${query}`, { method: "POST" }).then(setReplay).catch(e => setError(String(e)));
  const authorize = async () => {
    if (!replay || !selectedAction || !window.confirm("Authorize this simulated response? No physical switching or spacecraft command will occur.")) return;
    try {
      const result = await api<any>("/api/safe-mode/authorize", { method: "POST", headers: { "Content-Type": "application/json", "X-Hardware-Token": "development-token" }, body: JSON.stringify({ action: selectedAction, replay_index: replay.index }) });
      setEvents(previous => [...previous, result.event]);
    } catch (e) { setError(String(e)); }
  };
  if (error) return <main className="app-shell"><h1>Vexcel</h1><p className="error">{error}</p><HardwareControlDock /></main>;
  if (!activity || !investigation || !correlations || !replay) return <main className="app-shell"><p>Loading mission telemetry…</p><HardwareControlDock /></main>;
  const historyX = activity.series.map(point => point.timestamp);
  const historyY = activity.series.map(point => point.sym_h_nT);
  const stormX = investigation.series.map((point: Observation) => point.timestamp);
  const matrixText = correlations.coefficients.map(row => row.map(value => value === null ? "" : value.toFixed(2)));
  return <main className="app-shell">
    <header><p className="eyebrow">Vexcel / MISSION CONTROL</p><h1>Vexcel</h1><p className="lede">A compact view of geomagnetic activity, solar-wind coupling, and operator response.</p></header>
    <PrimaryNavigation activeSection={activeSection as "historical" | "investigation" | "correlations" | "mission"} onSelect={setActiveSection} />
    {activeSection === "historical" && <section id="historical" className="card"><h2>1. Historical Geomagnetic Activity</h2><p className="caption">{activity.coverage_start} to {activity.coverage_end} · {activity.observations.toLocaleString()} source rows</p><Chart data={[{ x: historyX, y: historyY, type: "scatter", mode: "lines", name: "SYM-H", line: { color: "#d8a56c" } }]} layout={{ height: 480, xaxis: { title: "UTC date" }, yaxis: { title: "SYM-H (nT)" }, shapes: [{ type: "rect", xref: "x", yref: "paper", x0: "2024-05-10", x1: "2024-05-12", y0: 0, y1: 1, fillcolor: "#9b5b2c", opacity: .18, line: { width: 0 } }], annotations: [{ x: activity.minimum_timestamp, y: activity.minimum_sym_h_nT, text: `Minimum ${activity.minimum_sym_h_nT} nT`, showarrow: true, arrowcolor: "#f5d6a5" }] }} /></section>}
    {activeSection === "investigation" && <section id="investigation" className="card"><h2>2. Storm Investigation</h2><p className="caption">Southward Bz onset precedes the measured SYM-H disturbance by <strong>{investigation.lead_minutes} minutes</strong>.</p><Chart data={[{ x: stormX, y: investigation.series.map((p: Observation) => p.bz_gsm_nT), name: "Bz GSM (nT)", mode: "lines", line: { color: "#d8a56c" } }, { x: stormX, y: investigation.series.map((p: Observation) => p.sym_h_nT), name: "SYM-H (nT)", mode: "lines", line: { color: "#f0eee8" } }]} layout={{ height: 430, xaxis: { title: "UTC" }, yaxis: { title: "nT" }, legend: { orientation: "h" } }} /></section>}
    {activeSection === "correlations" && <section id="correlations" className="card"><div className="section-heading"><div><h2>3. Solar Wind Correlations</h2><p className="caption">{correlations.explanation}</p></div><select value={correlationPeriod} onChange={event => setCorrelationPeriod(event.target.value)}><option value="all">Entire available dataset</option><option value="storm">May 10–11, 2024</option></select></div><Chart data={[{ z: correlations.coefficients, x: correlations.variables.map(v => `${v.label} (${v.unit})`), y: correlations.variables.map(v => `${v.label} (${v.unit})`), text: matrixText, texttemplate: "%{text}", type: "heatmap", zmin: -1, zmax: 1, colorscale: "RdBu", reversescale: true, hovertemplate: "%{y} × %{x}<br>r=%{z:.3f}<extra></extra>" }]} layout={{ height: 480, xaxis: { side: "bottom" }, yaxis: { autorange: "reversed" } }} /></section>}
    {activeSection === "mission" && <section id="mission" className="card mission"><h2>4. Mission Control</h2><div className="replay-header"><div><span className={`status ${replay.status}`}>{statusLabel(replay.status)}</span><strong>{replay.observation.timestamp}</strong></div><span>Observation {replay.index + 1} / {replay.total}</span></div><div className="metrics"><div><span className="label">Bz GSM</span><strong>{replay.observation.bz_gsm_nT ?? "Unavailable"} nT</strong></div><div><span className="label">SYM-H</span><strong>{replay.observation.sym_h_nT ?? "Unavailable"} nT</strong></div><div><span className="label">Progress</span><strong>{Math.round(replay.progress * 100)}%</strong></div></div><input aria-label="Replay position" type="range" min="0" max={replay.total - 1} value={replay.index} onChange={event => control("seek", `?index=${event.target.value}`)} /><div className="controls"><button onClick={() => control(replay.playing ? "pause" : "play")}>{replay.playing ? "Pause" : "Play"}</button><button onClick={() => control("step")}>Step</button><button onClick={() => control("reset")}>Reset</button>{[1, 2, 5, 10].map(speed => <button className={replay.speed === speed ? "selected" : ""} key={speed} onClick={() => control("speed", `?speed=${speed}`)}>{speed}x</button>)}</div><div className="safe-mode"><h3>SAFE MODE CONFIRMATION</h3><p className="caption">Simulation only. No electrical switching or spacecraft command is performed.</p><select value={selectedAction} onChange={event => setSelectedAction(event.target.value)}><option value="">Select simulated response</option><option value="grid_transformer_decoupling">Grid transformer decoupling simulation</option><option value="satellite_safe_orientation">Satellite array safe-orientation simulation</option></select><button disabled={!selectedAction} onClick={authorize}>SAFE MODE CONFIRMATION</button>{events.length > 0 && <p className="authorized">SAFE MODE AUTHORIZED — SIMULATION ONLY</p>}</div><div className="event-log"><h3>Operator event log</h3>{events.map(event => <div key={event.event_id}>{event.timestamp} · {event.action} · {event.event_id}</div>)}</div></section>}
    <HardwareControlDock />
  </main>;
}
createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
