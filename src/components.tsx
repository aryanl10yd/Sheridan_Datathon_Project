import type { ReactNode } from 'react';
import { AlertCircle, ArrowUpRight, ChevronRight, LoaderCircle } from 'lucide-react';
import type { Vulnerability } from './types';

export function Panel({ title, eyebrow, action, children, className = '' }: { title?: string; eyebrow?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}>
    {(title || eyebrow || action) && <div className="panel-head"><div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}{title && <h2>{title}</h2>}</div>{action}</div>}
    {children}
  </section>;
}
export function Badge({ children, tone = 'muted', dot = false }: { children: ReactNode; tone?: string; dot?: boolean }) {
  return <span className={`badge ${tone}`}>{dot && <span className="badge-dot" />}{children}</span>;
}
export function LoadState({ loading, error, empty, onRetry }: { loading?: boolean; error?: string; empty?: string; onRetry?: () => void }) {
  if (loading) return <div className="state-message"><LoaderCircle className="spin" size={17} /> Loading intelligence…</div>;
  if (error) return <div className="state-message error"><AlertCircle size={17} /><span>{error}</span>{onRetry && <button className="link-button" onClick={onRetry}>Retry</button>}</div>;
  if (empty) return <div className="state-message">{empty}</div>;
  return null;
}
export function formatDate(value?: string | null) {
  if (!value) return 'Not available';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric', timeZone: 'UTC' });
}
export function formatTime(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString('en-US', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }) + ' UTC';
}
export function display(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'Not available';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return value.map(display).join(' · ');
  return JSON.stringify(value, null, 2);
}
export function confidence(value: unknown) { return value === null || value === undefined ? 'Unknown' : typeof value === 'number' && value <= 1 ? `${value.toFixed(2)} (uncalibrated heuristic)` : String(value); }
export function momentumTone(label?: string) {
  const l = (label || '').toLowerCase();
  return l.includes('confirmed') || l.includes('increasing') ? 'red' : l.includes('emerging') || l.includes('persistent') ? 'amber' : 'muted';
}
export function RecordTable({ records, onSelect, compact = false }: { records: Vulnerability[]; onSelect: (record: Vulnerability) => void; compact?: boolean }) {
  if (!records.length) return <LoadState empty="No records match the current view." />;
  return <div className="table-wrap"><table><thead><tr><th>VULNERABILITY</th><th>CHARACTERISTICS</th><th>REVIEW</th><th>EXPLOITATION</th>{!compact && <th>PUBLISHED</th>}<th aria-label="Open" /></tr></thead><tbody>
    {records.map(record => <tr key={record.id} onClick={() => onSelect(record)} tabIndex={0} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(record); } }}>
      <td><span className="record-id">{record.id}</span><span className="record-sub">{[record.vendor, record.product].filter(Boolean).join(' / ') || 'Product not specified'}</span></td>
      <td><span className="table-characteristic">{record.characteristics?.[0]?.name || 'Not identified'}</span>{(record.characteristics?.length || 0) > 1 && <span className="extra-count"> +{(record.characteristics?.length || 0) - 1}</span>}</td>
      <td><Badge tone={(record.review_status || record.status || '').toLowerCase().includes('un') ? 'amber' : 'blue'}>{record.review_status || record.status || 'Unknown'}</Badge></td>
      <td><Badge tone={record.kev ? 'red' : momentumTone(record.momentum_label)} dot>{record.kev ? 'Reported KEV' : record.momentum_label || 'No assessment'}</Badge></td>
      {!compact && <td className="table-date">{formatDate(record.published)}</td>}
      <td><ChevronRight size={15} className="row-arrow" /></td>
    </tr>)}
  </tbody></table></div>;
}
export function RecordDetail({ record, onMomentum, onInvestigate }: { record: Vulnerability; onMomentum?: (id: string) => void; onInvestigate?: (id: string) => void }) {
  return <div className="record-detail">
    <div className="detail-heading"><div><div className="eyebrow">RECORD DETAIL / DATASET EVIDENCE</div><h2 className="mono">{record.id}</h2></div><Badge tone={record.kev ? 'red' : momentumTone(record.momentum_label)} dot>{record.kev ? 'Reported KEV' : record.momentum_label || 'No assessment'}</Badge></div>
    <p className="description">{record.description || 'Description not available.'}</p>
    <div className="detail-grid"><div><span>Published</span><strong>{formatDate(record.published)}</strong></div><div><span>Review status</span><strong>{record.review_status || record.status || 'Unknown'}</strong></div><div><span>CVSS</span><strong>{record.cvss ?? 'Unavailable'}</strong></div><div><span>EPSS</span><strong>{record.epss == null ? 'Unavailable' : record.epss}</strong></div><div><span>CWE</span><strong>{record.cwes?.join(', ') || 'Unavailable'}</strong></div><div><span>Source</span><strong>{record.source || 'Unavailable'}</strong></div></div>
    <h3 className="section-label">EXTRACTED CHARACTERISTICS</h3>
    {record.characteristics?.length ? record.characteristics.map((item, index) => <div className="characteristic" key={`${item.name}-${index}`}><div><strong>{item.name}</strong><span>Confidence: {confidence(item.confidence)}</span></div><p>{item.evidence ? `“${item.evidence}”` : 'Supporting text not provided.'}</p>{item.method && <p>Method: {item.method}</p>}{item.uncertainty && <p>Uncertainty: {item.uncertainty}</p>}</div>) : <p className="muted">No characteristics available.</p>}
    {record.references?.length ? <><h3 className="section-label">SOURCE REFERENCES</h3>{record.references.map((reference, index) => <div className="characteristic" key={index}><strong>{reference.source || 'Source not specified'}</strong><p>{reference.url || 'Reference URL unavailable'} · {formatDate(reference.date)}</p></div>)}</> : null}
    <p className="fine-print">Extracted characteristics are rule-based signals, not official classifications or proof of exploitation. Confidence values are uncalibrated heuristics.</p>
    <div className="button-row">{onMomentum && <button className="button secondary" onClick={() => onMomentum(record.id)}>View timeline <ArrowUpRight size={14} /></button>}{onInvestigate && <button className="button primary" onClick={() => onInvestigate(record.id)}>Investigate <ArrowUpRight size={14} /></button>}</div>
  </div>;
}
export function TextBlock({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === '') return <p className="muted">Not available.</p>;
  if (Array.isArray(value)) return <ul className="evidence-list">{value.map((entry, i) => <li key={i}>{typeof entry === 'object' ? <pre>{JSON.stringify(entry, null, 2)}</pre> : String(entry)}</li>)}</ul>;
  if (typeof value === 'object') return <pre className="structured">{JSON.stringify(value, null, 2)}</pre>;
  return <p className="body-copy">{String(value)}</p>;
}
