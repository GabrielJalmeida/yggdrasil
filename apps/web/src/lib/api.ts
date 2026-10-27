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

export interface QuestionAnswer {
  answer: string;
  citations: QuestionCitation[];
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
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
  graph: (id: string, options: { nodeType?: string; query?: string } = {}) => {
    const params = new URLSearchParams({ limit: '2000', edge_limit: '4000' });
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
