import { useEffect, useState } from 'react';
import { Search, SlidersHorizontal } from 'lucide-react';
import { useApi } from '../api';
import { LoadState, Panel, RecordDetail, RecordTable, TextBlock } from '../components';
import type { Overview, Vulnerability, VulnerabilityList } from '../types';

export default function ThreatExplorer({ selectedId, setSelectedId, navigate }: { selectedId: string; setSelectedId: (id: string) => void; navigate: (page: string) => void }) {
  const [compareInput, setCompareInput] = useState(''); const [compareId, setCompareId] = useState('');
  const [query, setQuery] = useState(''); const [debounced, setDebounced] = useState('');
  const [characteristic, setCharacteristic] = useState(''); const [status, setStatus] = useState(''); const [offset, setOffset] = useState(0);
  useEffect(() => { const timer = setTimeout(() => { setDebounced(query); setOffset(0); }, 300); return () => clearTimeout(timer); }, [query]);
  const params = new URLSearchParams({ q: debounced, characteristic, status, limit: '20', offset: String(offset) });
  const source = useApi<Overview>('/api/overview'); const quality = useApi<unknown>('/api/data-quality');
  const list = useApi<VulnerabilityList>(`/api/vulnerabilities?${params}`);
  const detail = useApi<Vulnerability>(selectedId ? `/api/vulnerabilities/${encodeURIComponent(selectedId)}` : null);
  const comparison = useApi<Vulnerability>(compareId ? `/api/vulnerabilities/${encodeURIComponent(compareId)}` : null);
  return <><div className="page-heading"><div><div className="breadcrumb">INTELLIGENCE <span>/</span> THREAT EXPLORER</div><h1>Threat Intelligence Explorer</h1><p>Search the underlying records. Follow the evidence, not just a score.</p></div></div>
    <div className="notice slim"><div className="notice-icon"><SlidersHorizontal size={16} /></div><div><strong>{source.data?.data_source || 'Data source unavailable'}</strong><span>Characteristics are analytical signals; unreviewed does not mean dangerous. Source claims are not independently verified.</span></div></div>
    <details className="panel spaced-panel"><summary>Data coverage and ingestion quality</summary><p className="fine-print">Missing or unsupported files limit the available evidence.</p>{quality.loading ? <LoadState loading /> : quality.error ? <LoadState error={quality.error} onRetry={quality.reload} /> : <TextBlock value={quality.data} />}</details>
    <div className="explorer-layout"><Panel title="Vulnerability records" eyebrow="SEARCH & FILTER" action={<span className="tiny-label">{list.data ? `${list.data.total.toLocaleString()} RECORDS` : '—'}</span>}>
      <div className="filters"><label className="search-field"><Search size={16} /><input aria-label="Search vulnerabilities" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search CVE ID or description" /></label><input aria-label="Filter by characteristic" className="filter-input" value={characteristic} onChange={event => { setCharacteristic(event.target.value); setOffset(0); }} placeholder="Characteristic" /><input aria-label="Filter by status" className="filter-input" value={status} onChange={event => { setStatus(event.target.value); setOffset(0); }} placeholder="Review status" /></div>
      {list.loading ? <LoadState loading /> : list.error ? <LoadState error={list.error} onRetry={list.reload} /> : <RecordTable records={list.data?.items || []} onSelect={record => setSelectedId(record.id)} />}
      <div className="panel-footer"><span>{list.data?.total ? `${offset + 1}–${Math.min(offset + 20, list.data.total)} of ${list.data.total}` : 'No records'}</span><div className="pagination"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}>Previous</button><button disabled={!list.data || offset + 20 >= list.data.total} onClick={() => setOffset(offset + 20)}>Next</button></div></div>
    </Panel><Panel className="detail-panel">{!selectedId ? <div className="empty-detail"><Search size={24} /><h3>Select a record</h3><p>Open a vulnerability to inspect its original description, characteristics and evidence.</p></div> : detail.loading ? <LoadState loading /> : detail.error ? <LoadState error={detail.error} onRetry={detail.reload} /> : detail.data && <RecordDetail record={detail.data} onMomentum={() => navigate('momentum')} onInvestigate={() => navigate('agents')} />}<div className="section-label">COMPARE A SECOND RECORD</div><form className="lookup" onSubmit={event => { event.preventDefault(); setCompareId(compareInput.trim()); }}><label className="search-field"><Search size={16} /><input aria-label="Comparison record ID" value={compareInput} onChange={event => setCompareInput(event.target.value)} placeholder="Second CVE or demo ID" /></label><button className="button secondary" disabled={!compareInput.trim()}>Compare</button></form>{compareId && (comparison.loading ? <LoadState loading /> : comparison.error ? <LoadState error={comparison.error} onRetry={comparison.reload} /> : comparison.data && <RecordDetail record={comparison.data} />)}</Panel></div>
  </>;
}
