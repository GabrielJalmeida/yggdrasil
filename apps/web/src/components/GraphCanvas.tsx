import { useEffect, useMemo, useState } from 'react';
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  type Edge,
  type Node,
  type NodeProps,
  useReactFlow,
} from '@xyflow/react';
import { Box, Braces, CircleDot, Code2, FileCode2, Folder, GitBranch, Package, ShieldAlert } from 'lucide-react';
import type { GraphEdge, GraphResponse } from '../lib/api';
import { createGraphPositions, pickVisibleNodes } from '../lib/graphLayout';

interface NodePayload extends Record<string, unknown> {
  label: string;
  kind: string;
  path: string | null;
  provenance: string;
  startLine: number | null;
  traceState: 'question-active' | 'question-cited' | 'question-retrieved' | 'scan-active' | 'scan-visited' | null;
}

interface GraphCanvasProps {
  graph: GraphResponse | null;
  filterType: string;
  searchQuery: string;
  selectedId: string | null;
  onSelect: (nodeId: string) => void;
  onLoadGraphPage: (offset: number) => Promise<GraphResponse | null>;
  loadingGraphPage: boolean;
  highlightedQuestionNodeIds: string[];
  citedQuestionNodeIds: string[];
  activeQuestionNodeIds: string[];
  highlightedScanNodeIds: string[];
  activeScanNodeIds: string[];
}

function iconFor(kind: string) {
  if (kind === 'repository') return <GitBranch size={15} />;
  if (kind === 'directory') return <Folder size={15} />;
  if (kind === 'file') return <FileCode2 size={15} />;
  if (kind === 'module') return <Braces size={15} />;
  if (kind === 'endpoint') return <CircleDot size={15} />;
  if (kind === 'dependency') return <Package size={15} />;
  if (kind === 'finding') return <ShieldAlert size={15} />;
  if (['class', 'model'].includes(kind)) return <Box size={15} />;
  return <Code2 size={15} />;
}

type RepositoryNode = Node<NodePayload, 'repositoryNode'>;

function GraphNodeCard({ data, selected }: NodeProps<RepositoryNode>) {
  return (
    <div className={`graph-node graph-node--${data.kind} ${selected ? 'is-selected' : ''} ${data.traceState ? `is-trace-${data.traceState}` : ''}`}>
      <Handle type="target" position={Position.Left} className="graph-handle" />
      <div className="graph-node__icon">{iconFor(data.kind)}</div>
      <div className="graph-node__copy">
        <span className="graph-node__kind">{data.kind.replaceAll('_', ' ')}</span>
        <strong title={data.label}>{data.label}</strong>
        {data.path && <small title={data.path}>{data.path.split('/').slice(-2).join('/')}{data.startLine ? ` · L${data.startLine}` : ''}</small>}
      </div>
      {data.provenance === 'inferred' && <span className="graph-node__inferred" title="Relações internas podem ter origem inferida">~</span>}
      <Handle type="source" position={Position.Right} className="graph-handle" />
    </div>
  );
}

const nodeTypes = { repositoryNode: GraphNodeCard };

function CanvasInner({
  graph, filterType, searchQuery, selectedId, onSelect, onLoadGraphPage, loadingGraphPage,
  highlightedQuestionNodeIds, citedQuestionNodeIds, activeQuestionNodeIds, highlightedScanNodeIds, activeScanNodeIds,
}: GraphCanvasProps) {
  const { fitView } = useReactFlow();
  const [pageOffset, setPageOffset] = useState(0);
  const filteredMode = filterType !== 'all' || Boolean(searchQuery.trim());
  useEffect(() => { setPageOffset(0); }, [filterType, searchQuery]);
  const highlightedNodeIds = useMemo(
    () => [...new Set([...highlightedQuestionNodeIds, ...highlightedScanNodeIds, ...activeQuestionNodeIds, ...activeScanNodeIds])],
    [activeQuestionNodeIds, activeScanNodeIds, highlightedQuestionNodeIds, highlightedScanNodeIds],
  );
  const activeQuestionSet = useMemo(() => new Set(activeQuestionNodeIds), [activeQuestionNodeIds]);
  const citedQuestionSet = useMemo(() => new Set(citedQuestionNodeIds), [citedQuestionNodeIds]);
  const questionSet = useMemo(() => new Set(highlightedQuestionNodeIds), [highlightedQuestionNodeIds]);
  const activeScanSet = useMemo(() => new Set(activeScanNodeIds), [activeScanNodeIds]);
  const scanSet = useMemo(() => new Set(highlightedScanNodeIds), [highlightedScanNodeIds]);
  const visibleRawNodes = useMemo(
    () => pickVisibleNodes(graph?.nodes ?? [], filterType, searchQuery, filteredMode ? pageOffset : 0, highlightedNodeIds),
    [filterType, filteredMode, graph?.nodes, highlightedNodeIds, pageOffset, searchQuery],
  );
  const flowNodes = useMemo(() => {
    const positions = createGraphPositions(visibleRawNodes);
    return visibleRawNodes.map((node): RepositoryNode => ({
      id: node.id,
      type: 'repositoryNode',
      position: positions.get(node.id) ?? { x: 0, y: 0 },
      selected: node.id === selectedId,
      data: {
        label: node.label,
        kind: node.type,
        path: node.path,
        provenance: node.provenance_type,
        startLine: node.start_line,
        traceState: activeQuestionSet.has(node.id) ? 'question-active'
          : citedQuestionSet.has(node.id) ? 'question-cited'
            : questionSet.has(node.id) ? 'question-retrieved'
              : activeScanSet.has(node.id) ? 'scan-active'
                : scanSet.has(node.id) ? 'scan-visited' : null,
      },
    }));
  }, [activeQuestionSet, activeScanSet, citedQuestionSet, questionSet, scanSet, selectedId, visibleRawNodes]);
  const ids = useMemo(() => new Set(flowNodes.map((node) => node.id)), [flowNodes]);
  const activeTraceSet = useMemo(
    () => new Set([...activeQuestionNodeIds, ...activeScanNodeIds]),
    [activeQuestionNodeIds, activeScanNodeIds],
  );
  const highlightedQuestionSet = useMemo(() => new Set(highlightedQuestionNodeIds), [highlightedQuestionNodeIds]);
  const flowEdges = useMemo(() => {
    const rows = (graph?.edges ?? []).filter((edge) => ids.has(edge.source) && ids.has(edge.target));
    return rows.slice(0, 1400).map((edge: GraphEdge): Edge => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.type,
      type: 'smoothstep',
      animated: false,
      style: activeTraceSet.has(edge.source) || activeTraceSet.has(edge.target)
        ? { stroke: '#f0bd67', strokeWidth: 2.8, opacity: 1 }
        : highlightedQuestionSet.has(edge.source) && highlightedQuestionSet.has(edge.target)
          ? { stroke: '#5ec8d5', strokeWidth: 2.0, opacity: 0.92 }
          : edge.provenance_type === 'inferred'
            ? { stroke: '#bd9bf5', strokeDasharray: '5 4', strokeWidth: 1.5 }
            : { stroke: '#536878', strokeWidth: 1.35 },
      labelStyle: { fill: '#9cafbd', fontSize: 10, fontWeight: 500 },
      labelBgStyle: { fill: '#111b24', fillOpacity: 0.94 },
      labelBgPadding: [4, 2] as [number, number],
    }));
  }, [activeTraceSet, graph?.edges, highlightedQuestionSet, ids]);

  useEffect(() => {
    if (!activeQuestionNodeIds.length && !activeScanNodeIds.length) return;
    const targetIds = new Set([...activeQuestionNodeIds, ...activeScanNodeIds]);
    const targets = flowNodes.filter((node) => targetIds.has(node.id));
    if (!targets.length) return;
    const timer = window.setTimeout(() => void fitView({ nodes: targets, padding: 0.42, duration: 320 }), 65);
    return () => window.clearTimeout(timer);
  }, [activeQuestionNodeIds, activeScanNodeIds, fitView, flowNodes]);

  const hasNextLoadedPage = Boolean(filteredMode && graph && pageOffset + 500 < graph.nodes.length);
  const hasMorePages = Boolean(filteredMode && graph && (hasNextLoadedPage || graph.has_more_nodes));
  const canGoPrevious = Boolean(filteredMode && graph && (pageOffset > 0 || graph.offset > 0));
  const pageStart = graph ? graph.offset + pageOffset + 1 : 0;
  const pageEnd = graph ? graph.offset + pageOffset + flowNodes.length : 0;

  const goNextPage = async () => {
    if (hasNextLoadedPage) {
      setPageOffset((current) => current + 500);
      return;
    }
    if (!graph?.has_more_nodes || loadingGraphPage) return;
    const next = await onLoadGraphPage(graph.offset + graph.returned_nodes);
    if (next) setPageOffset(0);
  };

  const goPreviousPage = async () => {
    if (pageOffset > 0) {
      setPageOffset((current) => Math.max(0, current - 500));
      return;
    }
    if (!graph || graph.offset <= 0 || loadingGraphPage) return;
    const previousOffset = Math.max(0, graph.offset - graph.page_size);
    const previous = await onLoadGraphPage(previousOffset);
    if (previous) setPageOffset(Math.max(0, Math.min(previous.page_size - 500, previous.returned_nodes - 500)));
  };

  useEffect(() => {
    if (flowNodes.length) {
      const timer = window.setTimeout(() => void fitView({ padding: 0.2, duration: 280 }), 70);
      return () => window.clearTimeout(timer);
    }
  }, [filterType, fitView, flowNodes.length, searchQuery]);

  if (!graph || graph.nodes.length === 0) {
    return (
      <div className="canvas-empty">
        <div className="canvas-empty__icon"><GitBranch size={24} /></div>
        <strong>O mapa começa aqui</strong>
        <p>Informe um repositório público do GitHub para inventariar arquivos e descobrir relações com evidências.</p>
      </div>
    );
  }
  if (!flowNodes.length) {
    return (
      <div className="canvas-empty">
        <div className="canvas-empty__icon"><CircleDot size={24} /></div>
        <strong>Nenhum nó corresponde ao filtro</strong>
        <p>Limpe a busca ou selecione outro tipo de componente.</p>
      </div>
    );
  }

  return (
    <>
    <ReactFlow<RepositoryNode, Edge>
      nodes={flowNodes}
      edges={flowEdges}
      nodeTypes={nodeTypes}
      onNodeClick={(_, node) => onSelect(node.id)}
      onPaneClick={() => onSelect('')}
      fitView
      minZoom={0.04}
      maxZoom={1.8}
      defaultEdgeOptions={{ type: 'smoothstep' }}
      proOptions={{ hideAttribution: true }}
    >
      <Background color="#263743" gap={22} size={1} />
      <Controls position="bottom-left" showInteractive={false} />
      <MiniMap
        position="bottom-right"
        pannable
        zoomable
        nodeColor={(node) => {
          const payload = node.data;
          if (payload.traceState === 'question-active' || payload.traceState === 'scan-active') return '#f0bd67';
          if (payload.traceState === 'question-cited') return '#9ce0b1';
          if (payload.traceState === 'question-retrieved') return '#5ec8d5';
          if (payload.traceState === 'scan-visited') return '#bd9bf5';
          if (payload.kind === 'finding') return '#f2b65c';
          if (payload.kind === 'endpoint') return '#69c9d5';
          if (payload.kind === 'repository') return '#9ce0b1';
          if (payload.provenance === 'inferred') return '#bd9bf5';
          return '#597283';
        }}
        maskColor="rgba(6, 10, 15, .74)"
        style={{ background: '#111a23' }}
      />
    </ReactFlow>
    {filterType === 'all' && !searchQuery.trim() && (
      <div className="canvas-view-note" role="status">
        <strong>VISÃO RESUMIDA</strong>
        <span>{flowNodes.length} visíveis no canvas · {graph.returned_nodes} nós retornados pela API · {graph.repository_total_nodes} nós no snapshot. Os omitidos desta visão continuam consultáveis pela busca.</span>
      </div>
    )}
    {filteredMode && (
      <>
        <div className="canvas-view-note canvas-view-note--filtered" role="status">
          <strong>EXPLORAÇÃO FILTRADA</strong>
          <span>Exibindo {pageStart}–{pageEnd} de {graph.total_nodes} resultados correspondentes · snapshot completo: {graph.repository_total_nodes} nós. A API retorna lotes de até {graph.page_size} nós e o canvas mostra até 500 por página.</span>
        </div>
        <div className="graph-page-controls" role="group" aria-label="Paginação dos resultados do grafo">
          <button type="button" onClick={() => void goPreviousPage()} disabled={!canGoPrevious || loadingGraphPage}>Anterior</button>
          <span>{loadingGraphPage ? 'Carregando lote…' : `${pageStart}–${pageEnd} / ${graph.total_nodes}`}</span>
          <button type="button" onClick={() => void goNextPage()} disabled={!hasMorePages || loadingGraphPage}>{loadingGraphPage ? 'Carregando…' : 'Próxima'}</button>
        </div>
      </>
    )}
    </>
  );
}

export function GraphCanvas(props: GraphCanvasProps) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  );
}
