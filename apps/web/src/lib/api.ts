export type AnalysisStatus =
  | 'queued'
  | 'fetching_repository'
  | 'inventorying'
  | 'parsing'
  | 'building_graph'
  | 'running_skills'
  | 'finalizing_report'
  | 'completed'
  | 'completed_with_warnings'
  | 'failed'
  | 'cancelled';

export interface AnalysisView {
  id: string;
  repository: { id: string; owner: string | null; name: string | null; canonical_url: string | null; default_branch: string | null };
  snapshot: null | { id: string; commit_sha: string; requested_ref: string; default_branch: string | null; metadata: Record<string, unknown> };
  status: AnalysisStatus;
  stage: string;
  progress: Record<string, number | string | null>;
  configuration: { skills?: string[]; ref?: string | null; ai_enabled?: boolean };
  error_code: string | null;
  warnings: string[];
  counts: { files: number; nodes: number; edges: number; findings: number };
  coverage: {
    inventory_total: number;
    eligible_files: number;
    ignored_by_policy: number;
    read_failures: number;
    unsupported_files: number;
    not_applicable_files: number;
    python_total: number;
    python_parsed: number;
    python_failed: number;
    python_pending: number;
    eligibility_status_counts?: Record<string, number>;
    parse_status_counts?: Record<string, number>;
    assessment?: 'pending' | 'partial' | 'observed';
    incomplete_reasons?: string[];
  };
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  events_url: string;
}

export interface GraphNode {
  id: string;
  type: string;
  stable_key: string;
  label: string;
  path: string | null;
  start_line: number | null;
  end_line: number | null;
  properties: Record<string, unknown>;
  provenance_type: string;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  provenance_type: string;
  confidence_label: string | null;
  evidence: Record<string, unknown>;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** Number of nodes matching the active server-side filters. */
  total_nodes: number;
  /** Number of edges matching the relation filter across the graph. */
  total_edges: number;
  /** Full snapshot counts, independent of search/node-type filters. */
  repository_total_nodes: number;
  repository_total_edges: number;
  returned_nodes: number;
  returned_edges: number;
  eligible_edges_for_returned_nodes: number;
  offset: number;
  page_size: number;
  has_more_nodes: boolean;
  truncated_nodes: boolean;
  truncated_edges: boolean;
  truncated: boolean;
}

export interface Finding {
  id: string;
  skill_id: string;
  skill_version: string;
  finding_key: string;
  category: string;
  severity: string;
  status: string;
  confidence_label: string;
  title: string;
  summary: string;
  impact: string;
  recommendation: string;
  limitations: string[];
  evidence: Array<{ path?: string; start_line?: number | null; end_line?: number | null; commit_sha?: string; evidence_type?: string; redacted?: boolean }>;
}

export type FindingReviewStatus =
  | 'confirmed'
  | 'needs_review'
  | 'not_reproducible'
  | 'accepted_risk'
  | 'false_positive'
  | 'fixed_in_revision';

export interface FindingStatusUpdateResponse {
  id: string;
  finding_key: string;
  previous_status: FindingReviewStatus;
  status: FindingReviewStatus;
  changed: boolean;
}

export interface QuestionCitation {
  id: string;
  kind: 'source_code' | 'finding' | 'graph_relation' | string;
  path: string | null;
  start_line: number | null;
  end_line: number | null;
  commit_sha: string;
  url: string | null;
  excerpt: string;
}

export interface QuestionTraceStep {
  evidence_id: string;
  rank: number;
  kind: string;
  path: string | null;
  start_line: number | null;
  end_line: number | null;
  node_ids: string[];
  cited: boolean;
}

export interface AnalysisPathStep {
  step_number: number;
  path: string;
  skill_id: string;
  node_ids: string[];
  source: 'deterministic_skill_scan';
}

export interface QuestionAnswer {
  answer: string;
  citations: QuestionCitation[];
  retrieval_trace?: QuestionTraceStep[];
  insufficient_evidence: boolean;
  evidence_count: number;
  provider: string;
  model: string;
  notice: string;
  question_intent?: string;
  question_intent_label?: string;
  retrieval_strategy?: string;
  retrieved_kinds?: string[];
}


export interface NodeDetail {
  node: GraphNode;
  commit_sha: string | null;
  evidence_url: string | null;
  code: string;
  code_start_line: number | null;
  redacted: boolean;
  message: string | null;
}

type YggdrasilDesktopWindow = Window & { __YGGDRASIL_API_TOKEN__?: string };

function desktopSessionHeaders(): Record<string, string> {
  const token = (window as YggdrasilDesktopWindow).__YGGDRASIL_API_TOKEN__;
  return token ? { 'X-Yggdrasil-Token': token } : {};
}

async function isDesktopSessionRejected(response: Response): Promise<boolean> {
  if (response.status !== 403) return false;
  try {
    const payload = await response.clone().json() as { detail?: { code?: string } | string };
    return typeof payload.detail === 'object' && payload.detail?.code === 'DESKTOP_TOKEN_REQUIRED';
  } catch {
    return false;
  }
}

async function refreshDesktopSessionToken(): Promise<boolean> {
  try {
    // The launcher rotates the per-process token when it restarts the API after a
    // settings change. Bootstrap is deliberately no-store and returns only that token.
    const response = await fetch('/desktop-bootstrap.js', {
      method: 'GET',
      cache: 'no-store',
      credentials: 'same-origin',
    });
    if (!response.ok) return false;
    const source = await response.text();
    const match = source.match(/window\.__YGGDRASIL_API_TOKEN__\s*=\s*"([A-Za-z0-9_-]+)";/);
    if (!match) return false;
    (window as YggdrasilDesktopWindow).__YGGDRASIL_API_TOKEN__ = match[1];
    return true;
  } catch {
    return false;
  }
}

async function fetchWithDesktopSessionRetry(path: string, init?: RequestInit): Promise<Response> {
  const send = () => {
    const headers = new Headers(init?.headers);
    if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
    for (const [name, value] of Object.entries(desktopSessionHeaders())) headers.set(name, value);
    return fetch(path, { ...init, headers });
  };

  let response = await send();
  if (await isDesktopSessionRejected(response) && await refreshDesktopSessionToken()) {
    response = await send();
  }
  return response;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetchWithDesktopSessionRetry(path, init);
  if (!response.ok) {
    let message = `Falha HTTP ${response.status}`;
    try {
      const payload = await response.json() as { detail?: { message?: string } | string };
      if (typeof payload.detail === 'string') message = payload.detail;
      else if (payload.detail?.message) message = payload.detail.message;
    } catch {
      // Keep the HTTP status as the fallback message.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const api = {
  createAnalysis: (body: { repository_url: string; ref?: string | null; profile: 'mvp-python'; skills: string[] }) =>
    request<{ id: string; repository_id: string; status: string; stage: string; events_url: string; analysis_url: string }>(
      '/api/v1/analyses', { method: 'POST', body: JSON.stringify(body) },
    ),
  analysis: (id: string) => request<AnalysisView>(`/api/v1/analyses/${id}`),
  graph: (id: string, options: { nodeType?: string; query?: string; offset?: number } = {}) => {
    const params = new URLSearchParams({ limit: '2000', offset: String(options.offset ?? 0), edge_limit: '4000' });
    if (options.nodeType && options.nodeType !== 'all') params.set('node_type', options.nodeType);
    if (options.query?.trim()) params.set('q', options.query.trim());
    return request<GraphResponse>(`/api/v1/analyses/${id}/graph?${params.toString()}`);
  },
  findings: (id: string) => request<{ items: Finding[]; total: number }>(`/api/v1/analyses/${id}/findings`),
  updateFindingStatus: (analysisId: string, findingId: string, status: FindingReviewStatus) =>
    request<FindingStatusUpdateResponse>(`/api/v1/analyses/${analysisId}/findings/${findingId}/status`, {
      method: 'PATCH', body: JSON.stringify({ status }),
    }),
  nodeDetail: (analysisId: string, nodeId: string) => request<NodeDetail>(`/api/v1/analyses/${analysisId}/nodes/${nodeId}`),
  ask: (analysisId: string, question: string) =>
    request<QuestionAnswer>(`/api/v1/analyses/${analysisId}/questions`, {
      method: 'POST', body: JSON.stringify({ question, scope: { node_ids: [], paths: [] } }),
    }),
  askStream: async (
    analysisId: string,
    question: string,
    onEvent: (eventType: string, payload: Record<string, unknown>) => void,
  ): Promise<QuestionAnswer> => {
    const response = await fetchWithDesktopSessionRetry(`/api/v1/analyses/${analysisId}/questions/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
      body: JSON.stringify({ question, scope: { node_ids: [], paths: [] } }),
    });
    if (!response.ok) {
      let message = `Falha HTTP ${response.status}`;
      try {
        const payload = await response.json() as { detail?: { message?: string } | string };
        if (typeof payload.detail === 'string') message = payload.detail;
        else if (payload.detail?.message) message = payload.detail.message;
      } catch { /* Keep HTTP status as the fallback. */ }
      throw new Error(message);
    }
    if (!response.body) throw new Error('O navegador não disponibilizou o fluxo de eventos da pergunta.');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let answer: QuestionAnswer | null = null;
    const consumeFrame = (frame: string) => {
      let eventType = 'message';
      const dataLines: string[] = [];
      for (const line of frame.split(/\r?\n/)) {
        if (line.startsWith('event:')) eventType = line.slice(6).trim();
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
      }
      if (!dataLines.length) return;
      let payload: Record<string, unknown>;
      try { payload = JSON.parse(dataLines.join('\n')) as Record<string, unknown>; }
      catch { throw new Error('O fluxo da pergunta retornou um evento inválido.'); }
      onEvent(eventType, payload);
      if (eventType === 'question_error') {
        const message = typeof payload.message === 'string' ? payload.message : 'A pergunta não pôde ser concluída.';
        throw new Error(message);
      }
      if (eventType === 'question_answer') answer = payload as unknown as QuestionAnswer;
    };
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let boundary = buffer.search(/\r?\n\r?\n/);
        while (boundary >= 0) {
          const delimiter = buffer.slice(boundary).match(/^\r?\n\r?\n/)?.[0] ?? '\n\n';
          consumeFrame(buffer.slice(0, boundary));
          buffer = buffer.slice(boundary + delimiter.length);
          boundary = buffer.search(/\r?\n\r?\n/);
        }
      }
      buffer += decoder.decode();
      if (buffer.trim()) consumeFrame(buffer);
    } finally {
      reader.releaseLock();
    }
    if (!answer) throw new Error('O fluxo terminou sem uma resposta final.');
    return answer;
  },
  health: () => request<{ status: string; database: string; version: string; ai_enabled: boolean; ai_provider: string; ai_model: string | null }>('/api/v1/health'),
};

export function isTerminal(status: AnalysisStatus): boolean {
  return ['completed', 'completed_with_warnings', 'failed', 'cancelled'].includes(status);
}

export function statusLabel(status: AnalysisStatus | string): string {
  const labels: Record<string, string> = {
    queued: 'Na fila', fetching_repository: 'Conectando ao GitHub', inventorying: 'Inventariando',
    parsing: 'Lendo estrutura Python', building_graph: 'Construindo o mapa', running_skills: 'Executando skills',
    finalizing_report: 'Finalizando relatório', completed: 'Concluída', completed_with_warnings: 'Concluída com avisos',
    failed: 'Falhou', cancelled: 'Cancelada',
  };
  return labels[status] ?? status;
}
