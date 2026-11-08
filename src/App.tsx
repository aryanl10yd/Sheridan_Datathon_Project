import { useEffect, useState } from 'react';
import { Activity, ArrowUpRight, Bot, ChevronDown, CircleHelp, FileText, Fingerprint, LayoutDashboard, Orbit, Radar, Search, Shield, ShieldCheck } from 'lucide-react';
import { useApi } from './api';
import CommandCenter from './pages/CommandCenter';
import ThreatExplorer from './pages/ThreatExplorer';
import Operations from './pages/Operations';
import MomentumPage from './pages/Momentum';
import Assurance from './pages/Assurance';
import Interlock from './pages/Interlock';
import Reports from './pages/Reports';
import type { Investigation, Overview } from './types';

const nav = [
  { id: 'command', label: 'Command Center', icon: LayoutDashboard, group: 'WORKSPACE' },
  { id: 'threats', label: 'Threat Explorer', icon: Search },
  { id: 'agents', label: 'Agent Operations', icon: Bot },
  { id: 'momentum', label: 'Exploitation Momentum', icon: Activity },
  { id: 'assurance', label: 'Mission Assurance', icon: ShieldCheck, group: 'MISSION CONTROL' },
  { id: 'interlock', label: 'Flight Interlock', icon: Fingerprint },
  { id: 'reports', label: 'Evidence Reports', icon: FileText, group: 'INTELLIGENCE' },
];
function currentPage() { const hash = window.location.hash.slice(1); return nav.some(item => item.id === hash) ? hash : 'command'; }
export default function App() {
  const [page, setPage] = useState(currentPage); const [selectedId, setSelectedId] = useState(''); const [investigation, setInvestigation] = useState<Investigation | null>(null); const overview = useApi<Overview>('/api/overview');
  useEffect(() => { const update = () => setPage(currentPage()); window.addEventListener('hashchange', update); return () => window.removeEventListener('hashchange', update); }, []);
  function navigate(id: string) { window.location.hash = id; setPage(id); window.scrollTo({ top: 0, behavior: 'smooth' }); }
  function selectRecord(id: string) { setSelectedId(id); navigate('threats'); }
  return <div className="app-shell"><aside className="sidebar"><div className="brand"><div className="brand-mark"><Orbit size={25} strokeWidth={1.5} /><span /></div><div><strong>SENTINEL<span> ORBITAL</span></strong><small>MISSION ASSURANCE SYSTEM</small></div></div><div className="workspace-select"><div className="workspace-icon"><Radar size={17} /></div><div><strong>Mission workspace</strong><small>Simulation environment</small></div><ChevronDown size={14} /></div><nav className="navigation" aria-label="Main navigation">{nav.map(item => <div key={item.id}>{item.group && <div className="nav-group">{item.group}</div>}<button className={`nav-item ${page === item.id ? 'active' : ''}`} onClick={() => navigate(item.id)}><item.icon size={17} strokeWidth={1.7} /><span>{item.label}</span>{page === item.id && <span className="active-marker" />}</button></div>)}</nav><div className="sidebar-bottom"><div className="sidebar-system"><span className="status-pulse" /><div><strong>Simulation mode</strong><small>Human authorization required</small></div></div><div className="sidebar-foot"><span>DEFENSIVE INTELLIGENCE</span><Shield size={14} /></div></div></aside>
    <div className="main-shell"><header className="topbar"><div className="topbar-left"><span className="topbar-kicker">SENTINEL ORBITAL</span><span className="topbar-divider" /><span>Mission operations</span></div><div className="topbar-right"><span className="top-data"><span className="mini-dot cyan" /> {overview.data?.mode || 'MODE UNAVAILABLE'}</span><span className="topbar-divider" /><button className="icon-button" aria-label="Open evidence reports" onClick={() => navigate('reports')}><CircleHelp size={17} /></button><div className="operator-avatar">SO</div><span className="operator-label">Operator <ChevronDown size={12} /></span></div></header><main className="content">{page === 'command' && <CommandCenter navigate={navigate} selectRecord={selectRecord} />}{page === 'threats' && <ThreatExplorer selectedId={selectedId} setSelectedId={setSelectedId} navigate={navigate} />}{page === 'agents' && <Operations selectedId={selectedId} result={investigation} setResult={setInvestigation} />}{page === 'momentum' && <MomentumPage selectedId={selectedId} setSelectedId={setSelectedId} />}{page === 'assurance' && <Assurance selectRecord={selectRecord} />}{page === 'interlock' && <Interlock />}{page === 'reports' && <Reports selectedId={selectedId} setSelectedId={setSelectedId} investigation={investigation} navigate={navigate} />}<footer className="content-footer"><span><span className="mini-dot cyan" /> SENTINEL ORBITAL / SIMULATION ENVIRONMENT</span><span>AI DISCOVERS. HUMANS AUTHORIZE. <ArrowUpRight size={12} /></span></footer></main></div></div>;
}
