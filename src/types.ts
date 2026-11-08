export interface Characteristic { name: string; evidence?: string; confidence?: string | number; method?: string; uncertainty?: string }
export interface Vulnerability {
  id: string; description?: string; published?: string; status?: string; cwes?: string[];
  cvss?: number | null; epss?: number | null; kev?: boolean; characteristics?: Characteristic[];
  vendor?: string; product?: string; source?: string; review_status?: string; momentum_label?: string;
  references?: { date?: string; url?: string; source?: string }[]; provenance?: unknown;
}
export interface Overview {
  mode: string; data_mode?: string; data_source: string;
  stats: { total: number; unenriched: number; known_exploited: number; with_signals: number };
  recent: Vulnerability[]; signals: Vulnerability[];
}
export interface VulnerabilityList { items: Vulnerability[]; total: number }
export interface Momentum { id: string; label: string; reason: string; events: { date: string; type?: string; kind?: string; value?: number | null; description: string; source: string }[]; limitations: string | string[] }
export interface Profile {
  name: string; description: string;
  inventory: { product: string; vendor: string; version: string }[];
  dependencies: { from: string; to: string }[];
  matches: { id: string; product: string; confidence: string | number; explanation: string }[];
}
export interface AgentResult { name: string; task: string; findings: unknown; evidence: unknown; tools: unknown; duration_ms: number; status: string }
export interface Investigation { mode: string; plan: unknown; agents: AgentResult[]; synthesis: unknown; verification: unknown; limitations: unknown }
export interface InterlockStatus {
  operation: string | null; state: string; approvals: { identity: string; at: string }[];
  device_connected: boolean; review_reason: string; audit: { at: string; event: string; detail: string }[];
  expires_at: string | null; mode: string; session_id: string | null;
}
