import { useEffect } from 'react';
import { Activity, ArrowRight, Crosshair, Fingerprint, Radio, ShieldAlert, ShieldCheck, Sparkles } from 'lucide-react';
import { useApi } from '../api';
import { Badge, formatDate, LoadState, Panel, RecordTable } from '../components';
import type { InterlockStatus, Overview, Vulnerability } from '../types';

export default function CommandCenter({ navigate, selectRecord }: { navigate: (page: string) => void; selectRecord: (id: string) => void }) {
  const overview = useApi<Overview>('/api/overview');
  const interlock = useApi<InterlockStatus>('/api/interlock/status');
  useEffect(() => { const timer = window.setInterval(interlock.reload, 5000); return () => window.clearInterval(timer); }, [interlock.reload]);
  useEffect(() => { const expires = interlock.data?.expires_at; const state = interlock.data?.state; if (!expires || (state !== 'review_required' && state !== 'approved')) return; const timer = window.setTimeout(interlock.reload, Math.max(0, new Date(expires).getTime() - Date.now()) + 20); return () => window.clearTimeout(timer); }, [interlock.data?.expires_at, interlock.data?.state, interlock.reload]);
  const data = overview.data;
  const metrics = [
    { label: 'VULNERABILITIES', value: data?.stats.total, caption: 'Records in dataset', icon: Crosshair, color: 'blue' },
    { label: 'NEEDS ENRICHMENT', value: data?.stats.unenriched, caption: 'Incomplete review', icon: Sparkles, color: 'amber' },
    { label: 'REPORTED KEV', value: data?.stats.known_exploited, caption: 'Source-reported records', icon: ShieldAlert, color: 'red' },
    { label: 'WITH SIGNALS', value: data?.stats.with_signals, caption: 'Exploitation indicators', icon: Activity, color: 'cyan' },
  ];
  return <>
    <div className="page-heading"><div><div className="breadcrumb">OPERATIONS <span>/</span> COMMAND CENTER</div><h1>Mission Command Center</h1><p>A unified view of emerging threats and mission assurance.</p></div><button className="button primary" onClick={() => navigate('agents')}><Sparkles size={16} /> New investigation <ArrowRight size={15} /></button></div>
    <div className="notice"><div className="notice-icon"><ShieldAlert size={17} /></div><div><strong>Simulation environment</strong><span>Fictional dataset and deterministic demo mode by default. No real flight operations or live command capability.</span></div><Badge tone="amber" dot>DEMO ONLY</Badge></div>
    <div className="metrics">{metrics.map(metric => <div className="metric" key={metric.label}><div className="metric-top"><span>{metric.label}</span><span className={`metric-icon ${metric.color}`}><metric.icon size={16} /></span></div><div className="metric-value">{metric.value === undefined ? '—' : metric.value.toLocaleString()}</div><div className="metric-caption"><span className={`mini-dot ${metric.color}`} />{metric.caption}</div></div>)}</div>
    {overview.error && <LoadState error={overview.error} onRetry={overview.reload} />}
    <div className="dashboard-grid"><div className="dashboard-main">
      <Panel title="Recent vulnerabilities" eyebrow="INTELLIGENCE FEED" action={<button className="text-action" onClick={() => navigate('threats')}>View explorer <ArrowRight size={14} /></button>}>
        <div className="panel-intro">Recently identified records from the current dataset.</div>
        {overview.loading ? <LoadState loading /> : <RecordTable records={data?.recent || []} onSelect={(record: Vulnerability) => selectRecord(record.id)} compact />}
        <div className="panel-footer"><span><span className="mini-dot cyan" /> DATA SOURCE: {data?.data_source || 'Unavailable'}</span><button className="text-action" onClick={() => navigate('threats')}>Explore all records <ArrowRight size={13} /></button></div>
      </Panel>
      <Panel title="Recent activity" eyebrow="OBSERVATION LOG" action={<span className="tiny-label">DATASET ACTIVITY</span>}>
        <div className="activity-list">{overview.loading ? <LoadState loading /> : data?.recent?.length ? data.recent.slice(0, 4).map((record, i) => <button className="activity-row" key={record.id} onClick={() => selectRecord(record.id)}><span className={`activity-marker ${i === 0 ? 'active' : ''}`}><span /></span><span className="activity-copy"><strong>{record.id}</strong><span>{record.characteristics?.[0]?.name || 'Vulnerability record'} · {record.review_status || record.status || 'Review status unavailable'}</span></span><span className="activity-date">{formatDate(record.published)}</span></button>) : <LoadState empty="No recent records available." />}</div>
      </Panel>
    </div><div className="dashboard-side">
      <Panel title="Flight interlock" eyebrow="HUMAN AUTHORIZATION" action={<Fingerprint size={18} className="icon-muted" />} className="interlock-card">
        <div className="interlock-visual"><div className="orbit-ring ring-one" /><div className="orbit-ring ring-two" /><div className="shield-center"><ShieldCheck size={28} strokeWidth={1.4} /></div><span className="orbit-dot" /></div>
        {interlock.loading ? <LoadState loading /> : interlock.error ? <LoadState error={interlock.error} onRetry={interlock.reload} /> : <><div className="interlock-title"><Badge tone={interlock.data?.state?.toLowerCase().includes('approved') ? 'cyan' : 'amber'} dot>{interlock.data?.state?.replaceAll('_', ' ') || 'Unavailable'}</Badge></div><p className="center-copy">{interlock.data?.operation || 'No simulated operation proposed.'}</p><div className="status-lines"><div><span>Device connection</span><strong><span className={`mini-dot ${interlock.data?.device_connected ? 'cyan' : 'red'}`} />{interlock.data?.device_connected ? 'Connected (mode-dependent)' : 'Disconnected'}</strong></div><div><span>Human approvals</span><strong>{interlock.data?.approvals?.length ?? '—'} / 2</strong></div></div></>}
        <button className="button secondary full" onClick={() => navigate('interlock')}>Open interlock console <ArrowRight size={14} /></button>
      </Panel>
      <Panel title="Signal watch" eyebrow="EXPLOITATION MOMENTUM" action={<Radio size={17} className="icon-muted" />}>
        <p className="side-intro">Records with available exploitation-related signals.</p>
        {overview.loading ? <LoadState loading /> : data?.signals?.length ? <div className="signal-list">{data.signals.slice(0, 3).map(record => <button className="signal-row" key={record.id} onClick={() => selectRecord(record.id)}><div><strong>{record.id}</strong><span>{record.product || 'Product not specified'}</span></div><Badge tone={record.kev ? 'red' : 'amber'}>{record.kev ? 'KEV' : record.momentum_label || 'Signal'}</Badge></button>)}</div> : <LoadState empty="No exploitation signals available." />}
        <button className="text-action bottom-action" onClick={() => navigate('momentum')}>View momentum <ArrowRight size={14} /></button>
      </Panel>
      <div className="source-note"><span className="source-icon">✳</span><div><strong>Evidence before assumptions</strong><p>Signals are not proof of exploitation. Review the source and limitations for each finding.</p></div></div>
    </div></div>
  </>;
}
