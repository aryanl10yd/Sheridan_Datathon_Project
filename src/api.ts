import { useCallback, useEffect, useState } from 'react';

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...options?.headers } });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (body.detail) message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
      else if (body.message) message = String(body.message);
    } catch { /* keep the HTTP status */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}
export function post<T>(path: string, body: unknown) {
  return api<T>(path, { method: 'POST', body: JSON.stringify(body) });
}
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(Boolean(path));
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => { setData(null); setLoading(true); setRevision(value => value + 1); }, []);
  useEffect(() => {
    if (!path) { setLoading(false); setData(null); return; }
    let active = true;
    setLoading(true); setError('');
    api<T>(path, path === '/api/interlock/status' ? { signal: AbortSignal.timeout(4000) } : undefined).then(result => { if (active) setData(result); }).catch(err => { if (active) { setData(null); setError(err instanceof Error ? err.message : 'Unable to load data'); } }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [path, revision]);
  return { data, loading, error, reload };
}
