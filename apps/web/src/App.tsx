import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  Clock3,
  Code2,
  ExternalLink,
  FileCode2,
  FileText,
  Fingerprint,
  GitBranch,
  GitCommitHorizontal,
  Layers3,
  LoaderCircle,
  LockKeyhole,
  MessageSquare,
  Minus,
  Network,
  Plus,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  ShieldAlert,
  Sparkles,
  TerminalSquare,
  Type,
  X,
} from 'lucide-react';
import { GraphCanvas } from './components/GraphCanvas';
import { api, isTerminal, statusLabel, type AnalysisView, type AnalysisPathStep, type Finding, type FindingReviewStatus, type GraphResponse, type NodeDetail, type QuestionAnswer, type QuestionTraceStep } from './lib/api';

const defaultSkills = ['appsec.secrets-detection', 'engineering.test-inventory'];
type FontScale = 'small' | 'normal' | 'large';
type FontFamily = 'system' | 'arial' | 'trebuchet';

function readDisplayPreference<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const value = window.localStorage.getItem(key);
    return value && allowed.includes(value as T) ? value as T : fallback;
  } catch {
    return fallback;
  }
}
const eventTitles: Record<string, string> = {
  analysis_queued: 'Análise colocada na fila',
  repository_fetch_started: 'Consultando metadados públicos',
  repository_metadata_loaded: 'Commit fixado para análise',
  selective_tree_fallback_started: 'ZIP grande; usando leitura seletiva por commit',
  inventory_completed: 'Inventário de arquivos concluído',
  graph_build_started: 'Construindo nós e relações',
  graph_build_completed: 'Mapa estático construído',
  skills_started: 'Skills determinísticas iniciadas',
  skills_completed: 'Inspeções iniciais concluídas',
  finding_created: 'Achado registrado para revisão',
  analysis_path_step: 'Varredura interativa de arquivo',
  finding_status_changed: 'Revisão de achado atualizada',
  analysis_completed: 'Análise finalizada',
  analysis_failed: 'A análise encontrou uma falha',
};

function prettyDate(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}

function shortSha(value?: string | null) {
  return value ? value.slice(0, 10) : 'aguardando';
}

function statusTone(status?: string) {
  if (status === 'completed') return 'success';
  if (status === 'completed_with_warnings') return 'warning';
  if (status === 'failed' || status === 'cancelled') return 'danger';
  return 'active';
}

function findingStatusLabel(status: string) {
  const labels: Record<string, string> = {
    confirmed: 'Confirmado',
    needs_review: 'Pendente de revisão',
    not_reproducible: 'Não reproduzível',
    accepted_risk: 'Risco aceito',
    false_positive: 'Falso positivo',
    fixed_in_revision: 'Corrigido em outra revisão',
  };
  return labels[status] ?? status.replaceAll('_', ' ');
}

const findingReviewStatuses: Array<{ value: FindingReviewStatus; label: string }> = [
  { value: 'needs_review', label: 'Pendente de revisão' },
  { value: 'confirmed', label: 'Confirmado' },
  { value: 'false_positive', label: 'Falso positivo' },
  { value: 'accepted_risk', label: 'Risco aceito' },
  { value: 'not_reproducible', label: 'Não reproduzível' },
  { value: 'fixed_in_revision', label: 'Corrigido em outra revisão' },
];

function activityDescription(eventType: string, payload: Record<string, unknown>) {
  if (eventType === 'repository_metadata_loaded') return `Commit ${String(payload.commit_sha ?? '').slice(0, 10)} fixado`;
  if (eventType === 'inventory_completed') return `${String(payload.files_discovered ?? 0)} arquivos encontrados`;
  if (eventType === 'graph_build_completed') return `${String(payload.nodes_created ?? 0)} nós · ${String(payload.edges_created ?? 0)} relações`;
  if (eventType === 'finding_created') return `${String(payload.severity ?? 'ACHADO')} · ${String(payload.title ?? 'Novo achado')}`;
  if (eventType === 'analysis_path_step') return `${String(payload.skill_id ?? 'skill')} · ${String(payload.path ?? 'arquivo')}`;
  if (eventType === 'analysis_failed') return String(payload.message ?? 'Verifique os detalhes da análise');
  if (eventType === 'analysis_path_step') return `${String(payload.skill_id ?? 'skill')} · ${String(payload.path ?? 'arquivo')}`;
  if (eventType === 'analysis_completed') return `${String(payload.findings_created ?? 0)} achados registrados`;
  return eventTitles[eventType] ?? eventType.replaceAll('_', ' ');
}

export function App() {
  const [repoUrl, setRepoUrl] = useState('');
  const [ref, setRef] = useState('');
  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisView | null>(null);
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [findingStatusFilter, setFindingStatusFilter] = useState('all');
  const [findingStatusDraft, setFindingStatusDraft] = useState<FindingReviewStatus>('needs_review');
  const [savingFindingStatus, setSavingFindingStatus] = useState(false);
  const [findingStatusMessage, setFindingStatusMessage] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [nodeDetail, setNodeDetail] = useState<NodeDetail | null>(null);
  const [filterType, setFilterType] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [backendReady, setBackendReady] = useState<boolean | null>(null);
  const [aiStatus, setAiStatus] = useState<{ enabled: boolean; provider: string; model: string | null } | null>(null);
  const [questionText, setQuestionText] = useState('');
  const [questionAnswer, setQuestionAnswer] = useState<QuestionAnswer | null>(null);
  const [questionError, setQuestionError] = useState<string | null>(null);
  const [askingQuestion, setAskingQuestion] = useState(false);
  const [questionTrace, setQuestionTrace] = useState<QuestionTraceStep[]>([]);
  const [activeQuestionTraceIndex, setActiveQuestionTraceIndex] = useState(-1);
  const [questionTraceStatus, setQuestionTraceStatus] = useState<'idle' | 'retrieving' | 'analyzing' | 'completed' | 'error'>('idle');
  const [analysisPathHistory, setAnalysisPathHistory] = useState<AnalysisPathStep[]>([]);
  const [activeAnalysisPath, setActiveAnalysisPath] = useState<AnalysisPathStep | null>(null);
  const scanPathQueueRef = useRef<AnalysisPathStep[]>([]);
  const [shareEvidenceConfirmed, setShareEvidenceConfirmed] = useState(false);
  const [fontScale, setFontScale] = useState<FontScale>(() => readDisplayPreference('yggdrasil.fontScale', ['small', 'normal', 'large'], 'normal'));
  const [fontFamily, setFontFamily] = useState<FontFamily>(() => readDisplayPreference('yggdrasil.fontFamily', ['system', 'arial', 'trebuchet'], 'system'));
  const [activities, setActivities] = useState<Array<{ id: string; title: string; description: string; time: string; eventType: string }>>([]);
  const [eventStreamStatus, setEventStreamStatus] = useState<'idle' | 'connecting' | 'connected' | 'reconnecting' | 'closed'>('idle');
  const [loadingGraphPage, setLoadingGraphPage] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const activeEventAnalysisRef = useRef<string | null>(null);
  const processedEventIdsRef = useRef<Set<string>>(new Set());
  const pollIntervalRef = useRef<number | null>(null);
  const loadedGraphForRef = useRef<string | null>(null);
  const loadedGraphAtTerminalForRef = useRef<string | null>(null);
  const loadedGraphFilterKeyRef = useRef<string | null>(null);
  const currentGraphFilterRef = useRef({ nodeType: 'all', query: '' });

  useEffect(() => {
    currentGraphFilterRef.current = { nodeType: filterType, query: searchQuery.trim() };
  }, [filterType, searchQuery]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      const next = scanPathQueueRef.current.shift();
      if (next) {
        setActiveAnalysisPath(next);
        setAnalysisPathHistory((previous) => [...previous.slice(-23), next]);
      }
    }, 220);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!askingQuestion || questionTrace.length < 2) return;
    const timer = window.setInterval(() => {
      setActiveQuestionTraceIndex((current) => (current + 1) % questionTrace.length);
    }, 720);
    return () => window.clearInterval(timer);
  }, [askingQuestion, questionTrace.length]);

  useEffect(() => {
    try {
      window.localStorage.setItem('yggdrasil.fontScale', fontScale);
      window.localStorage.setItem('yggdrasil.fontFamily', fontFamily);
    } catch {
      // Display preferences are optional; a blocked localStorage must not affect the app.
    }
  }, [fontScale, fontFamily]);

  useEffect(() => {
    api.health()
      .then((health) => {
        setBackendReady(true);
        setAiStatus({ enabled: health.ai_enabled, provider: health.ai_provider, model: health.ai_model });
      })
      .catch(() => { setBackendReady(false); setAiStatus(null); });
  }, []);

  const loadGraphAndFindings = useCallback(async (id: string): Promise<boolean> => {
    try {
      const filter = currentGraphFilterRef.current;
      const [nextGraph, nextFindings] = await Promise.all([
        api.graph(id, { nodeType: filter.nodeType, query: filter.query }),
        api.findings(id),
      ]);
      setGraph(nextGraph);
      setFindings(nextFindings.items);
      loadedGraphForRef.current = id;
      loadedGraphFilterKeyRef.current = `${filter.nodeType}|${filter.query}`;
      return true;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Não foi possível carregar o mapa.');
      return false;
    }
  }, []);

  const loadGraphPage = useCallback(async (offset: number): Promise<GraphResponse | null> => {
    if (!analysisId) return null;
    setLoadingGraphPage(true);
    try {
      const filter = currentGraphFilterRef.current;
      const nextGraph = await api.graph(analysisId, { nodeType: filter.nodeType, query: filter.query, offset });
      setGraph(nextGraph);
      loadedGraphForRef.current = analysisId;
      loadedGraphFilterKeyRef.current = `${filter.nodeType}|${filter.query}`;
      return nextGraph;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Não foi possível carregar a próxima página do grafo.');
      return null;
    } finally {
      setLoadingGraphPage(false);
    }
  }, [analysisId]);

  useEffect(() => {
    if (!analysisId || !analysis || !isTerminal(analysis.status) || loadedGraphForRef.current !== analysisId) return;
    const query = searchQuery.trim();
    const nodeType = filterType === 'all' ? undefined : filterType;
    const key = `${nodeType ?? 'all'}|${query}`;
    if (loadedGraphFilterKeyRef.current === key) return;

    let cancelled = false;
    const timer = window.setTimeout(() => {
      void api.graph(analysisId, { nodeType, query }).then((nextGraph) => {
        if (cancelled) return;
        setGraph(nextGraph);
        loadedGraphFilterKeyRef.current = key;
      }).catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : 'Não foi possível filtrar o mapa.');
      });
    }, 300);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [analysisId, analysis, filterType, searchQuery]);

  const refreshAnalysis = useCallback(async (id: string) => {
    try {
      const nextAnalysis = await api.analysis(id);
      setAnalysis(nextAnalysis);
      if (nextAnalysis.snapshot && (nextAnalysis.stage === 'running_skills' || isTerminal(nextAnalysis.status))) {
        // Fetch the baseline graph once. Terminal polling must not reload thousands of nodes
        // every two seconds; domain events and the explicit refresh button update it as needed.
        const terminal = isTerminal(nextAnalysis.status);
        const mustRefreshTerminalGraph = terminal && loadedGraphAtTerminalForRef.current !== id;
        if (loadedGraphForRef.current !== id || mustRefreshTerminalGraph) {
          const loaded = await loadGraphAndFindings(id);
          if (loaded && terminal) loadedGraphAtTerminalForRef.current = id;
        }
      }
      if (isTerminal(nextAnalysis.status)) {
        eventSourceRef.current?.close();
        eventSourceRef.current = null;
        setEventStreamStatus('closed');
        if (pollIntervalRef.current !== null) {
          window.clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Não foi possível atualizar o estado da análise.');
    }
  }, [loadGraphAndFindings]);

  useEffect(() => {
    if (!analysisId) { setEventStreamStatus('idle'); return; }
    if (activeEventAnalysisRef.current !== analysisId) {
      activeEventAnalysisRef.current = analysisId;
      processedEventIdsRef.current.clear();
    }
    setEventStreamStatus('connecting');
    void refreshAnalysis(analysisId);
    const pollId = window.setInterval(() => void refreshAnalysis(analysisId), 2000);
    pollIntervalRef.current = pollId;
    const source = new EventSource(`/api/v1/analyses/${analysisId}/events`);
    eventSourceRef.current = source;
    source.onopen = () => setEventStreamStatus('connected');
    const eventNames = [
      'analysis_queued', 'repository_fetch_started', 'repository_metadata_loaded', 'inventory_completed',
      'graph_build_started', 'graph_build_completed', 'skills_started', 'skills_completed',
      'finding_created', 'analysis_path_step', 'analysis_completed', 'analysis_failed', 'file_ignored', 'analysis_warning',
    ];
    const listeners = eventNames.map((eventType) => {
      const listener = (event: Event) => {
        const message = event as MessageEvent<string>;
        const sequenceId = message.lastEventId?.trim();
        if (sequenceId && processedEventIdsRef.current.has(sequenceId)) return;
        if (sequenceId) {
          processedEventIdsRef.current.add(sequenceId);
          if (processedEventIdsRef.current.size > 500) {
            const oldest = processedEventIdsRef.current.values().next().value;
            if (oldest) processedEventIdsRef.current.delete(oldest);
          }
        }
        let payload: Record<string, unknown> = {};
        try { payload = JSON.parse(message.data) as Record<string, unknown>; } catch { /* Empty payload is safe. */ }
        if (eventType === 'analysis_path_step' && typeof payload.path === 'string' && Array.isArray(payload.node_ids)) {
          const step: AnalysisPathStep = {
            step_number: Number(payload.step_number ?? 0),
            path: payload.path,
            skill_id: String(payload.skill_id ?? 'skill'),
            node_ids: payload.node_ids.filter((value): value is string => typeof value === 'string'),
            source: 'deterministic_skill_scan',
          };
          scanPathQueueRef.current.push(step);
          // Bound replay after reconnects; the queue always represents real persisted events.
          if (scanPathQueueRef.current.length > 90) scanPathQueueRef.current = scanPathQueueRef.current.slice(-90);
        }
        if (eventType !== 'analysis_path_step') setActivities((previous) => [
          {
            id: `${message.lastEventId || Date.now()}-${eventType}`,
            title: eventTitles[eventType] ?? eventType.replaceAll('_', ' '),
            description: activityDescription(eventType, payload),
            time: new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            eventType,
          },
          ...previous,
        ].slice(0, 9));
        if (eventType === 'graph_build_completed' || eventType === 'skills_completed' || eventType === 'analysis_completed') {
          void loadGraphAndFindings(analysisId);
          void refreshAnalysis(analysisId);
        }
        if (eventType === 'analysis_failed') void refreshAnalysis(analysisId);
      };
      source.addEventListener(eventType, listener);
      return () => source.removeEventListener(eventType, listener);
    });
    source.onerror = () => {
      // EventSource retries with its persisted Last-Event-ID; API polling remains the fallback.
      setEventStreamStatus(source.readyState === EventSource.CONNECTING ? 'reconnecting' : 'closed');
    };
    return () => {
      window.clearInterval(pollId);
      if (pollIntervalRef.current === pollId) pollIntervalRef.current = null;
      listeners.forEach((remove) => remove());
      source.close();
      if (eventSourceRef.current === source) eventSourceRef.current = null;
    };
  }, [analysisId, loadGraphAndFindings, refreshAnalysis]);

  useEffect(() => {
    if (!analysisId || !selectedId) {
      setNodeDetail(null);
      return;
    }
    let cancelled = false;
    api.nodeDetail(analysisId, selectedId)
      .then((detail) => { if (!cancelled) setNodeDetail(detail); })
      .catch(() => { if (!cancelled) setNodeDetail(null); });
    return () => { cancelled = true; };
  }, [analysisId, selectedId]);

  const startAnalysis = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!repoUrl.trim()) {
      setError('Informe a URL de um repositório público do GitHub.');
      return;
    }
    setError(null);
    setSubmitting(true);
    eventSourceRef.current?.close();
    loadedGraphForRef.current = null;
    setAnalysis(null);
    setGraph(null);
    setFindings([]);
    setFindingStatusFilter('all');
    setFindingStatusMessage(null);
    setSelectedId(null);
    setQuestionText('');
    setQuestionAnswer(null);
    setQuestionError(null);
    setQuestionTrace([]);
    setActiveQuestionTraceIndex(-1);
    setQuestionTraceStatus('idle');
    setAnalysisPathHistory([]);
    setActiveAnalysisPath(null);
    scanPathQueueRef.current = [];
    setShareEvidenceConfirmed(false);
    setActivities([]);
    setEventStreamStatus('idle');
    processedEventIdsRef.current.clear();
    activeEventAnalysisRef.current = null;
    try {
      const created = await api.createAnalysis({
        repository_url: repoUrl.trim(),
        ref: ref.trim() || null,
        profile: 'mvp-python',
        skills: defaultSkills,
      });
      setAnalysisId(created.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Não foi possível iniciar a análise.');
    } finally {
      setSubmitting(false);
    }
  };

  const currentFinding = useMemo(() => {
    const key = nodeDetail?.node.properties.finding_key;
    return typeof key === 'string' ? findings.find((finding) => finding.finding_key === key) ?? null : null;
  }, [findings, nodeDetail]);

  useEffect(() => {
    if (currentFinding) setFindingStatusDraft(currentFinding.status as FindingReviewStatus);
  }, [currentFinding]);

  const visibleFindings = useMemo(
    () => findings.filter((finding) => findingStatusFilter === 'all' || finding.status === findingStatusFilter),
    [findings, findingStatusFilter],
  );

  const saveFindingReviewStatus = async () => {
    if (!analysisId || !currentFinding) return;
    setSavingFindingStatus(true);
    setFindingStatusMessage(null);
    try {
      const result = await api.updateFindingStatus(analysisId, currentFinding.id, findingStatusDraft);
      await loadGraphAndFindings(analysisId);
      if (selectedId) {
        try { setNodeDetail(await api.nodeDetail(analysisId, selectedId)); } catch { /* Current detail may be unavailable for an old selection. */ }
      }
      setFindingStatusMessage(result.changed ? `Revisão salva: ${findingStatusLabel(result.status)}.` : 'Esse status já estava selecionado.');
      setActivities((previous) => [{
        id: `review-${Date.now()}`,
        title: 'Revisão de achado atualizada',
        description: `${currentFinding.title} · ${findingStatusLabel(result.status)}`,
        time: new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        eventType: 'finding_status_changed',
      }, ...previous].slice(0, 9));
    } catch (cause) {
      setFindingStatusMessage(cause instanceof Error ? cause.message : 'Não foi possível salvar a revisão.');
    } finally {
      setSavingFindingStatus(false);
    }
  };

  const isRunning = Boolean(analysis && !isTerminal(analysis.status));
  const canAskQuestions = Boolean(analysis && ['completed', 'completed_with_warnings'].includes(analysis.status));
  const submitQuestion = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!analysisId || !questionText.trim() || !aiStatus?.enabled || !canAskQuestions || !shareEvidenceConfirmed) return;
    setAskingQuestion(true);
    setQuestionError(null);
    setQuestionAnswer(null);
    setQuestionTrace([]);
    setActiveQuestionTraceIndex(-1);
    setQuestionTraceStatus('retrieving');
    try {
      const answer = await api.askStream(analysisId, questionText.trim(), (eventType, payload) => {
        if (eventType === 'question_started') setQuestionTraceStatus('retrieving');
        if (eventType === 'question_retrieval' && Array.isArray(payload.steps)) {
          setQuestionTrace(payload.steps as QuestionTraceStep[]);
          setActiveQuestionTraceIndex(0);
          setQuestionTraceStatus('analyzing');
        }
      });
      setQuestionAnswer(answer);
      setQuestionTrace(answer.retrieval_trace ?? []);
      setQuestionTraceStatus('completed');
      setActiveQuestionTraceIndex(-1);
    } catch (cause) {
      setQuestionTraceStatus('error');
      setActiveQuestionTraceIndex(-1);
      setQuestionError(cause instanceof Error ? cause.message : 'Não foi possível responder à pergunta.');
    } finally {
      setAskingQuestion(false);
    }
  };
  const progress = analysis?.progress ?? {};
  const filesProcessed = Number(progress.files_processed ?? 0);
  const totalFiles = typeof progress.total_files === 'number' ? progress.total_files : null;

  return (
    <div className="app-shell" data-font-scale={fontScale} data-font-family={fontFamily}>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Yggdrasil início">
          <span className="brand-mark"><GitBranch size={20} strokeWidth={2.3} /></span>
          <span className="brand-name">yggdrasil<span>.</span></span>
          <span className="brand-divider" />
          <span className="brand-subtitle">repository intelligence</span>
        </a>
        <div className="topbar-right">
          <div className={`connection-pill ${backendReady === true ? 'is-ready' : backendReady === false ? 'is-error' : ''}`}>
            <span className="connection-dot" />
            {backendReady === true ? 'API conectada' : backendReady === false ? 'API indisponível' : 'Verificando API'}
          </div>
          <details className="display-settings">
            <summary aria-label="Preferências de fonte e tamanho"><Type size={14} /><span>Texto</span><ChevronRight size={12} /></summary>
            <div className="display-settings-popover">
              <label htmlFor="display-font-family">Fonte</label>
              <select id="display-font-family" value={fontFamily} onChange={(event) => setFontFamily(event.target.value as FontFamily)}>
                <option value="system">Sistema / Inter</option>
                <option value="arial">Arial</option>
                <option value="trebuchet">Trebuchet MS</option>
              </select>
              <span className="display-settings-label">Tamanho do texto</span>
              <div className="display-settings-size-row">
                <button type="button" aria-label="Diminuir tamanho do texto" title="Diminuir tamanho do texto" disabled={fontScale === 'small'} onClick={() => setFontScale(fontScale === 'large' ? 'normal' : 'small')}><Minus size={13} /><span>A−</span></button>
                <strong>{fontScale === 'small' ? 'Pequeno' : fontScale === 'large' ? 'Grande' : 'Normal'}</strong>
                <button type="button" aria-label="Aumentar tamanho do texto" title="Aumentar tamanho do texto" disabled={fontScale === 'large'} onClick={() => setFontScale(fontScale === 'small' ? 'normal' : 'large')}><Plus size={13} /><span>A+</span></button>
              </div>
              <button className="display-settings-reset" type="button" onClick={() => { setFontScale('normal'); setFontFamily('system'); }}>Restaurar padrão</button>
            </div>
          </details>
          <span className="version-tag">MVP 0.7.0</span>
        </div>
      </header>

      <main id="top" className="app-main">
        <section className="intro-row">
          <div>
            <div className="eyebrow"><span className="eyebrow-line" /> MAPA DE CONHECIMENTO <span className="eyebrow-dot">/</span> ANÁLISE ESTÁTICA</div>
            <h1>Entenda o código.<br /><span>Enxergue as conexões.</span></h1>
            <p className="intro-copy">Transforme um repositório em um mapa técnico rastreável — com evidências, não palpites.</p>
          </div>
          <div className="intro-side-note">
            <div className="note-icon"><ShieldCheck size={18} /></div>
            <div><strong>Somente leitura</strong><span>O código analisado nunca é executado.</span></div>
          </div>
        </section>

        <section className="connect-card" aria-label="Iniciar uma análise">
          <div className="connect-card__heading">
            <div className="connect-icon"><GitBranch size={18} /></div>
            <div><strong>Comece por um repositório</strong><span>GitHub público · commit fixado · parsing Python</span></div>
            <div className="connect-badge"><LockKeyhole size={12} /> READ ONLY</div>
          </div>
          <form className="repo-form" onSubmit={startAnalysis}>
            <label className="repo-input-wrap">
              <span className="input-prefix"><GitBranch size={16} /></span>
              <input
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="https://github.com/owner/repository"
                aria-label="URL do repositório público"
                autoComplete="url"
              />
            </label>
            <label className="ref-input-wrap">
              <span>REF</span>
              <input value={ref} onChange={(e) => setRef(e.target.value)} placeholder="main" aria-label="Branch ou referência Git" />
            </label>
            <button className="primary-button" type="submit" disabled={submitting || !backendReady}>
              {submitting ? <LoaderCircle className="spin" size={16} /> : <Sparkles size={16} />}
              {submitting ? 'Preparando…' : 'Mapear repositório'}
              {!submitting && <ArrowRight size={15} />}
            </button>
          </form>
          <div className="connect-foot">
            <span><Check size={13} /> Sem instalação no repositório-alvo</span>
            <span><Check size={13} /> Sem executar builds ou testes</span>
            <span><Check size={13} /> Conteúdo textual armazenado com padrões de segredo redigidos</span>
          </div>
        </section>

        {error && (
          <div className="error-banner" role="alert">
            <AlertCircle size={17} /><span>{error}</span>
            <button type="button" onClick={() => setError(null)} aria-label="Fechar aviso"><X size={16} /></button>
          </div>
        )}

        {!analysis && !analysisId && (
          <section className="welcome-grid">
            <div className="welcome-main panel">
              <div className="section-eyebrow">PRIMEIRO FLUXO VERTICAL</div>
              <h2>De uma URL a um mapa que você pode investigar.</h2>
              <p>O Yggdrasil fixa um commit, inventaria arquivos, extrai estrutura Python e conecta componentes usando evidências localizáveis.</p>
              <div className="flow-steps">
                <div className="flow-step"><span>01</span><GitCommitHorizontal size={17} /><strong>Resolver commit</strong><small>Versão imutável</small></div>
                <ChevronRight size={15} className="flow-separator" />
                <div className="flow-step"><span>02</span><Code2 size={17} /><strong>Extrair estrutura</strong><small>Sem executar código</small></div>
                <ChevronRight size={15} className="flow-separator" />
                <div className="flow-step"><span>03</span><Network size={17} /><strong>Construir grafo</strong><small>Relações rastreáveis</small></div>
                <ChevronRight size={15} className="flow-separator" />
                <div className="flow-step"><span>04</span><FileText size={17} /><strong>Exportar mapa</strong><small>Markdown portátil</small></div>
              </div>
              <div className="example-repo-row">
                <span>EXEMPLO PÚBLICO</span>
                <button type="button" onClick={() => { setRepoUrl('https://github.com/psf/requests'); setRef('main'); }}>
                  <span className="example-dot" /> psf/requests <ArrowUpRight size={13} />
                </button>
                <small>Preenche o campo; nada é iniciado automaticamente.</small>
              </div>
            </div>
            <div className="welcome-side">
              <div className="mini-feature panel">
                <span className="feature-icon feature-icon--cyan"><Network size={17} /></span>
                <div><strong>Grafo com origem</strong><p>Arquivos, módulos, símbolos, endpoints e dependências reconhecidas.</p></div>
                <span className="feature-index">01</span>
              </div>
              <div className="mini-feature panel">
                <span className="feature-icon feature-icon--amber"><ShieldAlert size={17} /></span>
                <div><strong>Achados revisáveis</strong><p>Severidade, evidência, confiança qualitativa e limitações visíveis.</p></div>
                <span className="feature-index">02</span>
              </div>
              <div className="mini-feature panel">
                <span className="feature-icon feature-icon--violet"><FileText size={17} /></span>
                <div><strong>Relatório portátil</strong><p>Markdown ligado ao commit, não a uma conversa de IA.</p></div>
                <span className="feature-index">03</span>
              </div>
              <div className="ai-note"><Sparkles size={15} /><span><strong>IA desligada neste MVP.</strong> A análise determinística funciona sem chave externa.</span></div>
            </div>
          </section>
        )}

        {analysisId && (
          <section className="workspace-section">
            <div className="run-header panel">
              <div className="run-header__left">
                <div className={`status-orb status-orb--${statusTone(analysis?.status)}`}>
                  {isRunning ? <LoaderCircle className="spin" size={17} /> : analysis?.status === 'failed' ? <AlertCircle size={17} /> : <GitBranch size={17} />}
                </div>
                <div>
                  <div className="run-title-line"><h2>{analysis?.repository?.owner && analysis.repository.name ? `${analysis.repository.owner}/${analysis.repository.name}` : repoUrl}</h2><span className={`status-tag status-tag--${statusTone(analysis?.status)}`}>{statusLabel(analysis?.status ?? 'queued')}</span></div>
                  <div className="run-subtitle">
                    <span><GitCommitHorizontal size={13} /> {shortSha(analysis?.snapshot?.commit_sha)}</span>
                    <span className="run-subtitle-dot">·</span>
                    <span>ref: {(analysis?.snapshot?.requested_ref ?? ref) || 'branch padrão'}</span>
                    <span className="run-subtitle-dot">·</span>
                    <span>iniciada {prettyDate(analysis?.created_at)}</span>
                    {typeof progress.ingestion_method === 'string' && <><span className="run-subtitle-dot">·</span><span>ingestão: {progress.ingestion_method === 'github_tree' ? 'leitura seletiva' : 'arquivo compactado'}</span></>}
                  </div>
                </div>
              </div>
              <div className="run-header__actions">
                {analysis?.snapshot?.commit_sha && analysis?.repository?.canonical_url && (
                  <a className="ghost-button" href={`${analysis.repository.canonical_url}/commit/${analysis.snapshot.commit_sha}`} target="_blank" rel="noreferrer"><ExternalLink size={14} /> Commit</a>
                )}
                {analysis?.snapshot && <a className="primary-button primary-button--small" href={`/api/v1/analyses/${analysisId}/export/markdown`}><ArrowDownToLine size={15} /> Exportar Markdown</a>}
              </div>
            </div>

            <div className="metric-grid">
              <MetricCard icon={<FileCode2 size={16} />} label="Arquivos" value={analysis?.counts.files ?? 0} caption="Inventariados" />
              <MetricCard icon={<Network size={16} />} label="Nós" value={analysis?.counts.nodes ?? 0} caption="No grafo de conhecimento" />
              <MetricCard icon={<GitBranch size={16} />} label="Relações" value={analysis?.counts.edges ?? 0} caption="Determinísticas + inferidas" />
              <MetricCard icon={<ShieldAlert size={16} />} label="Achados" value={analysis?.counts.findings ?? 0} caption="Para revisão humana" highlight={(analysis?.counts.findings ?? 0) > 0} />
            </div>
            {analysis?.coverage && isTerminal(analysis.status) && (
              <section className="coverage-inline" aria-label="Cobertura da ingestão">
                <div className="coverage-inline__heading">
                  <strong>Cobertura da ingestão</strong>
                  <span>{analysis.coverage.inventory_total} arquivos inventariados</span>
                </div>
                <div className="coverage-inline__stats">
                  <span><strong>{analysis.coverage.eligible_files}</strong> elegíveis / conteúdo lido</span>
                  <span><strong>{analysis.coverage.ignored_by_policy}</strong> ignorados por política</span>
                  <span><strong>{analysis.coverage.read_failures}</strong> falhas de leitura</span>
                  <span><strong>{analysis.coverage.python_parsed}/{analysis.coverage.python_total}</strong> arquivos Python parseados</span>
                  <span><strong>{analysis.coverage.python_failed}</strong> falhas de parsing Python</span>
                  <span><strong>{analysis.coverage.unsupported_files}</strong> ignorados por formato/limite</span>
                  <span><strong>{analysis.coverage.not_applicable_files}</strong> fora do parsing Python</span>
                </div>
                <p>Estes números descrevem o inventário e os estados de parsing. Categorias de elegibilidade e parsing são dimensões diferentes e podem referir-se ao mesmo arquivo. O limite do mapa é independente.</p>
                {analysis.coverage.assessment === 'partial' && analysis.coverage.incomplete_reasons?.length ? (
                  <div className="coverage-inline__diagnostic" role="status"><strong>Escopo parcial conhecido</strong><ul>{analysis.coverage.incomplete_reasons.map((reason, index) => <li key={`${index}-${reason}`}>{reason}</li>)}</ul></div>
                ) : null}
              </section>
            )}

            {isRunning && (
              <div className="stage-strip panel">
                <div className="stage-strip__top"><span><LoaderCircle className="spin" size={14} /> {statusLabel(analysis?.status ?? 'queued')}</span><span>{totalFiles !== null ? `${filesProcessed} / ${totalFiles} arquivos` : 'Etapas e contadores reais · sem porcentagem inventada'}</span></div>
                <div className="stage-track">
                  {['GitHub', 'Inventário', 'Parsing', 'Grafo', 'Skills', 'Relatório'].map((label, index) => {
                    const current = ['fetching_repository', 'inventorying', 'parsing', 'building_graph', 'running_skills', 'finalizing_report'].indexOf(analysis?.stage ?? 'queued');
                    const done = index < current;
                    const active = index === current;
                    return <div className={`stage-step ${done ? 'is-done' : ''} ${active ? 'is-current' : ''}`} key={label}><span>{done ? <Check size={11} /> : index + 1}</span>{label}</div>;
                  })}
                </div>
              </div>
            )}

            {analysis?.status === 'failed' && (
              <div className="error-banner error-banner--persistent"><AlertTriangle size={17} /><span><strong>{analysis.error_code ?? 'Falha de análise'}.</strong> {analysis.warnings[0] ?? 'A análise não foi concluída.'}</span></div>
            )}
            {analysis?.warnings?.length ? (
              <div className="warning-inline" role="status">
                <AlertTriangle size={14} />
                <div className="warning-inline__content">
                  <strong>{analysis.warnings.length} aviso(s) de ingestão, cobertura ou itens ignorados</strong>
                  <ul>{analysis.warnings.map((warning, index) => <li key={`${index}-${warning}`}>{warning}</li>)}</ul>
                </div>
              </div>
            ) : null}

            <section className="question-panel panel" aria-labelledby="question-panel-title">
              <div className="question-panel-heading">
                <div className="question-panel-icon"><MessageSquare size={17} /></div>
                <div className="question-panel-title-wrap">
                  <span className="section-eyebrow">IA / RECUPERAÇÃO DE EVIDÊNCIAS</span>
                  <h3 id="question-panel-title">Pergunte ao repositório</h3>
                  <p>Respostas baseadas em trechos recuperados do snapshot e referências verificáveis.</p>
                </div>
                <span className={`question-provider-tag ${aiStatus?.enabled ? 'is-enabled' : 'is-disabled'}`}>
                  {aiStatus?.enabled ? `IA ativa · ${aiStatus.provider}` : 'IA não configurada'}
                </span>
              </div>

              {!aiStatus?.enabled ? (
                <div className="question-config-note">
                  <ShieldCheck size={16} />
                  <div>
                    <strong>A análise determinística continua funcionando sem IA.</strong>
                    <p>Para habilitar perguntas, configure no arquivo <code>.env</code> da raiz o provedor compatível, o modelo e a chave (quando exigida), depois reinicie a API. Veja o README e o <code>.env.example</code> para opções de configuração.</p>
                  </div>
                </div>
              ) : (
                <>
                  <div className="question-privacy-note"><LockKeyhole size={14} /><span>Privacidade: ao enviar, somente trechos relevantes já redigidos e metadados de evidência serão enviados ao provedor configurado — não o repositório inteiro. Configure apenas um provedor em que confie.</span></div>
                  <form className="question-form" onSubmit={(event) => void submitQuestion(event)}>
                    <label className="question-input-label" htmlFor="repository-question">SUA PERGUNTA</label>
                    <textarea
                      id="repository-question"
                      value={questionText}
                      onChange={(event) => setQuestionText(event.target.value)}
                      placeholder="Ex.: Onde a aplicação configura o acesso ao banco de dados?"
                      maxLength={1500}
                      rows={3}
                      disabled={!canAskQuestions || askingQuestion}
                    />
                    <div className="question-form-footer">
                      <label className="question-consent"><input type="checkbox" checked={shareEvidenceConfirmed} onChange={(event) => setShareEvidenceConfirmed(event.target.checked)} disabled={askingQuestion} /> Entendo que os trechos redigidos recuperados serão enviados ao provedor configurado.</label>
                      <button className="question-submit" type="submit" disabled={!canAskQuestions || !shareEvidenceConfirmed || !questionText.trim() || askingQuestion}>
                        {askingQuestion ? <LoaderCircle size={14} className="spin" /> : <Send size={14} />} {askingQuestion ? 'Consultando evidências…' : 'Perguntar'}
                      </button>
                    </div>
                    {!canAskQuestions && <p className="question-hint">As perguntas ficam disponíveis depois que a análise terminar com sucesso.</p>}
                  </form>
                </>
              )}

              {questionError && <div className="question-error" role="alert"><AlertCircle size={15} /><span>{questionError}</span></div>}
              {questionAnswer && (
                <div className={`question-answer ${questionAnswer.insufficient_evidence ? 'is-inconclusive' : ''}`}>
                  <div className="question-answer-heading"><Sparkles size={15} /><strong>{questionAnswer.insufficient_evidence ? 'Resposta inconclusiva' : 'Resposta baseada nas evidências'}</strong><span>{questionAnswer.provider} · {questionAnswer.model}</span></div>
                  <p className="question-answer-text">{questionAnswer.answer}</p>
                  {questionAnswer.question_intent_label && (
                    <div className="question-answer-contextline">
                      <span>Contexto utilizado</span>
                      <strong>{questionAnswer.question_intent_label}</strong>
                      <small>{questionAnswer.evidence_count} evidências{questionAnswer.retrieved_kinds?.length ? ` · ${questionAnswer.retrieved_kinds.join(', ')}` : ''}</small>
                    </div>
                  )}
                  {questionAnswer.retrieval_strategy && (
                    <p className="question-answer-strategy">Estratégia de recuperação: {questionAnswer.retrieval_strategy}</p>
                  )}
                  {questionAnswer.citations.length > 0 && (
                    <details className="question-citations">
                      <summary className="question-citations-summary">
                        <BookOpen size={13} />
                        <span>FONTES RECUPERADAS</span>
                        <small>{questionAnswer.citations.length} referências · abrir para consultar</small>
                        <ChevronRight size={14} className="question-citations-chevron" />
                      </summary>
                      <div className="question-citations-list">
                        {questionAnswer.citations.map((citation) => (
                          <article className="question-citation" key={citation.id}>
                            <div className="question-citation-top"><span>{citation.id}</span><strong>{citation.path ?? citation.kind}</strong><small>{citation.start_line ? `L${citation.start_line}${citation.end_line && citation.end_line !== citation.start_line ? `–${citation.end_line}` : ''}` : citation.kind}</small>
                              {citation.url && <a href={citation.url} target="_blank" rel="noreferrer" aria-label={`Abrir ${citation.path ?? citation.id} no commit analisado`}><ExternalLink size={13} /></a>}
                            </div>
                            <pre>{citation.excerpt}</pre>
                          </article>
                        ))}
                      </div>
                    </details>
                  )}
                  <p className="question-answer-notice">{questionAnswer.notice}</p>
                </div>
              )}
              {questionTrace.length > 0 && (
                <section className="question-trace" aria-label="Trilha visual das evidências">
                  <div className="question-trace__heading">
                    <div><span className="question-trace__eyebrow">EXPLORAÇÃO VISUAL</span><strong>Trilha da pergunta</strong></div>
                    <span className={`question-trace__status is-${questionTraceStatus}`}>{questionTraceStatus === 'retrieving' ? 'Recuperando…' : questionTraceStatus === 'analyzing' ? 'Modelo analisando contexto…' : questionTraceStatus === 'error' ? 'Interrompida' : 'Evidências prontas'}</span>
                  </div>
                  <p>Os destaques mostram os arquivos e nós realmente recuperados. Verde indica evidência citada; ciano, recuperada; âmbar, passo atual. Isto não revela raciocínio interno do modelo.</p>
                  <div className="question-trace__steps">
                    {questionTrace.map((step, index) => (
                      <button type="button" key={`${step.evidence_id}-${step.path ?? 'profile'}-${index}`} className={`question-trace__step ${activeQuestionTraceIndex === index && askingQuestion ? 'is-active' : ''} ${step.cited ? 'is-cited' : ''}`} onClick={() => { setActiveQuestionTraceIndex(index); if (step.node_ids[0]) setSelectedId(step.node_ids[0]); }}>
                        <span className="question-trace__rank">{step.evidence_id}</span>
                        <span className="question-trace__path"><strong>{step.path ?? 'Perfil do repositório'}</strong><small>{step.start_line ? `L${step.start_line}${step.end_line && step.end_line !== step.start_line ? `–${step.end_line}` : ''}` : step.kind.replaceAll('_', ' ')}</small></span>
                        <span className={`question-trace__kind ${step.cited ? 'is-cited' : ''}`}>{step.cited ? 'Citada' : 'Recuperada'}</span>
                      </button>
                    ))}
                  </div>
                  <button type="button" className="question-trace__clear" onClick={() => { setQuestionTrace([]); setActiveQuestionTraceIndex(-1); setQuestionTraceStatus('idle'); }}>Limpar destaques</button>
                </section>
              )}
            </section>

            <div className="workspace-grid">
              <aside className="left-rail">
                <section className="rail-section panel">
                  <div className="rail-heading"><span>EXPLORAÇÃO</span><Layers3 size={14} /></div>
                  <label className="search-box"><Search size={14} /><input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="Buscar nó ou caminho" /></label>
                  <label className="filter-select-label" htmlFor="node-filter">TIPO DE COMPONENTE</label>
                  <select id="node-filter" className="filter-select" value={filterType} onChange={(event) => setFilterType(event.target.value)}>
                    <option value="all">Todos os tipos</option>
                    <option value="repository">Repositório</option>
                    <option value="directory">Diretórios</option>
                    <option value="file">Arquivos</option>
                    <option value="module">Módulos</option>
                    <option value="class">Classes</option>
                    <option value="model">Modelos</option>
                    <option value="function">Funções</option>
                    <option value="method">Métodos</option>
                    <option value="test">Testes identificados</option>
                    <option value="endpoint">Endpoints</option>
                    <option value="dependency">Dependências</option>
                    <option value="finding">Achados</option>
                  </select>
                  <div className="legend-list">
                    <div><span className="legend-dot legend-dot--solid" /> Extraído diretamente</div>
                    <div><span className="legend-dot legend-dot--dashed" /> Relação inferida</div>
                    <div><span className="legend-dot legend-dot--finding" /> Achado para revisão</div>
                  </div>
                  {graph?.truncated && (
                    <p className="graph-limit-note" role="status">
                      <AlertTriangle size={12} />
                      <span>
                        {graph.truncated_nodes && `Nós: resultados ${graph.offset + 1}–${graph.offset + graph.returned_nodes} de ${graph.total_nodes} correspondentes (grafo completo: ${graph.repository_total_nodes}). Use Próxima para continuar a navegação. `}
                        Relações: {graph.returned_edges} retornadas de {graph.eligible_edges_for_returned_nodes} possíveis entre os nós carregados; o grafo completo possui {graph.repository_total_edges}. Busca e filtros consultam o servidor. Este aviso é sobre o limite desta visualização e não confirma, por si só, ingestão incompleta; confira também os avisos da análise.
                      </span>
                    </p>
                  )}
                </section>

                <section className="rail-section panel activity-panel">
                  <div className="rail-heading"><span>ATIVIDADE RECENTE</span><span className={`event-stream-status event-stream-status--${eventStreamStatus}`} role="status">{eventStreamStatus === 'connected' ? 'SSE conectado' : eventStreamStatus === 'reconnecting' ? 'Reconectando · polling ativo' : eventStreamStatus === 'connecting' ? 'Conectando SSE' : eventStreamStatus === 'closed' ? 'Fluxo encerrado' : 'Aguardando fluxo'}</span><Clock3 size={14} /></div>
                  {activities.length ? (
                    <div className="activity-list">
                      {activities.slice(0, 7).map((item) => (
                        <div className="activity-item" key={item.id}>
                          <span className={`activity-marker ${item.eventType === 'analysis_failed' ? 'activity-marker--error' : item.eventType === 'finding_created' ? 'activity-marker--finding' : ''}`} />
                          <div><strong>{item.title}</strong><p>{item.description}</p><time>{item.time}</time></div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="activity-empty"><Clock3 size={16} /><span>Os eventos desta análise aparecerão aqui.</span></div>
                  )}
                </section>
              </aside>

              <section className="canvas-column">
                <div className="canvas-toolbar">
                  <div><span className="canvas-live-dot" /><h3>Mapa de conhecimento</h3><span className="canvas-kicker">SNAPSHOT FIXADO</span></div>
                  <div className="canvas-toolbar__meta"><span><CircleHelp size={13} /> Clique em um nó para inspecionar</span><button type="button" onClick={() => analysisId && void loadGraphAndFindings(analysisId)} title="Atualizar mapa"><RefreshCw size={14} /></button></div>
                </div>
                <div className="canvas-frame">
                  {graph ? (
                    <GraphCanvas
                      graph={graph}
                      filterType={filterType}
                      searchQuery={searchQuery}
                      selectedId={selectedId}
                      onSelect={(id) => setSelectedId(id || null)}
                      onLoadGraphPage={loadGraphPage}
                      loadingGraphPage={loadingGraphPage}
                      highlightedQuestionNodeIds={[...new Set(questionTrace.flatMap((step) => step.node_ids))]}
                      citedQuestionNodeIds={[...new Set(questionTrace.filter((step) => step.cited).flatMap((step) => step.node_ids))]}
                      activeQuestionNodeIds={activeQuestionTraceIndex >= 0 ? questionTrace[activeQuestionTraceIndex]?.node_ids ?? [] : []}
                      highlightedScanNodeIds={[...new Set(analysisPathHistory.flatMap((step) => step.node_ids))]}
                      activeScanNodeIds={activeAnalysisPath?.node_ids ?? []}
                    />
                  ) : (
                    <div className="canvas-wait"><div className="canvas-wait__symbol"><GitBranch size={28} /></div><strong>{isRunning ? 'Preparando as evidências…' : 'Mapa ainda indisponível'}</strong><p>{isRunning ? 'O grafo aparece quando a estrutura está persistida; depois disso, os eventos reais das skills destacam os arquivos inspecionados.' : 'A análise não produziu um grafo consultável.'}</p>{isRunning && <LoaderCircle className="spin wait-spinner" size={17} />}</div>
                  )}
                  {activeAnalysisPath && (
                    <div className="graph-trace-status graph-trace-status--scan" role="status">
                      <span className="graph-trace-status__dot" />
                      <div><strong>{isRunning ? 'Varredura determinística em andamento' : 'Último passo registrado da varredura'}</strong><span>{activeAnalysisPath.skill_id} · {activeAnalysisPath.path}</span></div>
                      <small>passo {activeAnalysisPath.step_number}</small>
                    </div>
                  )}
                  {questionTrace.length > 0 && (
                    <div className="graph-trace-status graph-trace-status--question" role="status">
                      <span className="graph-trace-status__dot" />
                      <div><strong>{askingQuestion ? 'Trilha visual da pergunta' : 'Nós ligados à pergunta'}</strong><span>{askingQuestion ? 'Percorrendo evidências reais antes da resposta do modelo' : `${questionTrace.filter((step) => step.cited).length} evidência(s) citada(s) · ${questionTrace.length} recuperada(s)`}</span></div>
                    </div>
                  )}
                  <div className="canvas-footnote"><span>GRAFO ESTÁTICO</span><span>Trilhas baseadas em eventos e evidências reais · sem execução de código do repositório</span></div>
                </div>

                <section className="findings-section panel">
                  <div className="findings-heading">
                    <div><span className="findings-heading__icon"><ShieldAlert size={16} /></span><div><h3>Achados e revisão</h3><p>Resultados determinísticos, com estado de revisão persistido.</p></div></div>
                    <div className="findings-tools">
                      <label className="finding-filter-label" htmlFor="finding-status-filter">STATUS</label>
                      <select id="finding-status-filter" className="finding-status-filter" value={findingStatusFilter} onChange={(event) => setFindingStatusFilter(event.target.value)}>
                        <option value="all">Todos</option>
                        {findingReviewStatuses.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}
                      </select>
                      <span className="findings-count">{visibleFindings.length}/{findings.length}</span>
                    </div>
                  </div>
                  {findings.length ? (visibleFindings.length ? (
                    <div className="finding-list">
                      {visibleFindings.map((finding) => (
                        <button className={`finding-row ${selectedId && nodeDetail?.node.properties.finding_key === finding.finding_key ? 'is-active' : ''}`} type="button" key={finding.id} onClick={() => {
                          setFindingStatusMessage(null);
                          const graphNode = graph?.nodes.find((node) => node.properties.finding_key === finding.finding_key);
                          if (graphNode) setSelectedId(graphNode.id);
                        }}>
                          <span className={`finding-severity finding-severity--${finding.severity.toLowerCase()}`}>{finding.severity}</span>
                          <span className="finding-copy"><strong>{finding.title}</strong><small>{finding.skill_id} · confiança {finding.confidence_label} · {findingStatusLabel(finding.status)}</small></span>
                          <ChevronRight size={15} />
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div className="findings-empty"><CheckCircle2 size={17} /><div><strong>Nenhum achado nesse status</strong><p>Altere o filtro para ver os demais resultados.</p></div></div>
                  )) : (
                    <div className="findings-empty"><CheckCircle2 size={17} /><div><strong>{analysis?.status && isTerminal(analysis.status) ? 'Nenhum achado registrado pelas skills habilitadas' : 'As skills ainda não terminaram'}</strong><p>Ausência de achados não significa ausência de problemas ou vulnerabilidades.</p></div></div>
                  )}
                </section>
              </section>

              <aside className="inspector panel">
                <div className="inspector-header"><div><span className="section-eyebrow">INSPECTOR</span><h3>Detalhes e evidências</h3></div><span className="inspector-status"><Fingerprint size={15} /></span></div>
                {nodeDetail ? (
                  <div className="inspector-body">
                    <div className={`inspector-node-type inspector-node-type--${nodeDetail.node.type}`}><span>{nodeDetail.node.type.replaceAll('_', ' ')}</span><span className={`provenance-tag provenance-tag--${nodeDetail.node.provenance_type}`}>{nodeDetail.node.provenance_type === 'inferred' ? 'inferido' : 'determinístico'}</span></div>
                    <h4 className="inspector-node-title">{nodeDetail.node.label}</h4>
                    {nodeDetail.node.path && <div className="file-location"><FileCode2 size={13} /><span>{nodeDetail.node.path}</span></div>}
                    {nodeDetail.node.start_line && <div className="line-range">Linhas {nodeDetail.node.start_line}{nodeDetail.node.end_line && nodeDetail.node.end_line !== nodeDetail.node.start_line ? `–${nodeDetail.node.end_line}` : ''}</div>}
                    {nodeDetail.evidence_url && <a href={nodeDetail.evidence_url} target="_blank" rel="noreferrer" className="evidence-link">Abrir no commit analisado <ExternalLink size={13} /></a>}
                    <div className="inspector-divider" />
                    {currentFinding && (
                      <div className="inspector-finding">
                        <div className="finding-detail-heading"><span className={`finding-severity finding-severity--${currentFinding.severity.toLowerCase()}`}>{currentFinding.severity}</span><span>{findingStatusLabel(currentFinding.status)}</span></div>
                        <p>{currentFinding.summary}</p>
                        <div className="finding-review-controls">
                          <label htmlFor="finding-review-status">REVISÃO HUMANA</label>
                          <div className="finding-review-row">
                            <select id="finding-review-status" value={findingStatusDraft} onChange={(event) => setFindingStatusDraft(event.target.value as FindingReviewStatus)} disabled={!analysis || !isTerminal(analysis.status) || savingFindingStatus}>
                              {findingReviewStatuses.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}
                            </select>
                            <button type="button" onClick={() => void saveFindingReviewStatus()} disabled={!analysis || !isTerminal(analysis.status) || savingFindingStatus || findingStatusDraft === currentFinding.status}>
                              {savingFindingStatus ? <LoaderCircle size={13} className="spin" /> : <Check size={13} />} Salvar
                            </button>
                          </div>
                          {findingStatusMessage && <p className="finding-status-message" role="status">{findingStatusMessage}</p>}
                          {!analysis || !isTerminal(analysis.status) ? <small>A revisão fica disponível quando a análise terminar.</small> : <small>Essa decisão organiza a triagem; não altera o código nem a evidência do commit analisado.</small>}
                        </div>
                        <div className="inspector-label">IMPACTO POTENCIAL</div><p>{currentFinding.impact}</p>
                        <div className="inspector-label">RECOMENDAÇÃO</div><p>{currentFinding.recommendation}</p>
                        <div className="inspector-label">LIMITAÇÕES</div>
                        <ul>{currentFinding.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
                      </div>
                    )}
                    <div className="inspector-label">PROPRIEDADES EXTRAÍDAS</div>
                    <div className="property-list">
                      {Object.entries(nodeDetail.node.properties).filter(([, value]) => value !== null && value !== undefined && typeof value !== 'object').slice(0, 12).map(([key, value]) => (
                        <div className="property-row" key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{String(value)}</strong></div>
                      ))}
                    </div>
                    {nodeDetail.code ? (
                      <>
                        <div className="code-toolbar"><span><TerminalSquare size={13} /> TRECHO DO CÓDIGO</span><span>SEGREDOS REDIGIDOS</span></div>
                        <pre className="code-inspector"><code>{nodeDetail.code}</code></pre>
                      </>
                    ) : <div className="no-code-note"><BookOpen size={15} /><span>{nodeDetail.message ?? 'Não existe trecho de código associado a este nó.'}</span></div>}
                    <div className="inspector-safe-note"><LockKeyhole size={13} /> Trechos persistidos com padrões de segredo redigidos. A detecção pode ter falsos negativos.</div>
                  </div>
                ) : (
                  <div className="inspector-empty">
                    <div className="inspector-empty__icon"><Network size={24} /></div>
                    <strong>Selecione um componente</strong>
                    <p>O inspetor mostra caminho, linhas, metadados, proveniência e o trecho de código associado, quando disponível.</p>
                    <div className="inspector-tip"><Sparkles size={14} /><span>Relações inferidas aparecem com linha tracejada no mapa.</span></div>
                  </div>
                )}
                <div className="inspector-footer"><span>YGGDRASIL / STATIC ANALYSIS</span><span>v0.7.0</span></div>
              </aside>
            </div>

            <div className="workspace-bottom-note"><ShieldCheck size={14} /><span>Este mapa descreve apenas o que foi reconhecido no snapshot fixado. Arquivos ignorados, parsing parcial e limites reduzem a cobertura; não é uma auditoria completa de segurança.</span><button type="button" onClick={() => { setAnalysisId(null); setAnalysis(null); setGraph(null); setFindings([]); setSelectedId(null); setActivities([]); setQuestionTrace([]); setActiveQuestionTraceIndex(-1); setAnalysisPathHistory([]); setActiveAnalysisPath(null); scanPathQueueRef.current = []; }}><X size={13} /> Fechar análise</button></div>
          </section>
        )}
      </main>

      <footer className="app-footer"><span>YGGDRASIL © 2026</span><span>Mapa antes de palpite <i /> Evidência antes de conclusão</span><span><span className="footer-status-dot" /> ANÁLISE DE SOMENTE LEITURA</span></footer>
    </div>
  );
}

function MetricCard({ icon, label, value, caption, highlight = false }: { icon: ReactNode; label: string; value: number; caption: string; highlight?: boolean }) {
  return (
    <div className={`metric-card panel ${highlight ? 'metric-card--highlight' : ''}`}>
      <div className="metric-card__top"><span>{icon}</span><span>{label}</span></div>
      <strong>{value.toLocaleString('pt-BR')}</strong>
      <small>{caption}</small>
    </div>
  );
}
