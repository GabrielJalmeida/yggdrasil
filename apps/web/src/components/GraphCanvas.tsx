import { useEffect, useMemo } from 'react';
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

interface NodePayload {
  label: string;
  kind: string;
  path: string | null;
  provenance: string;
  startLine: number | null;
}

interface GraphCanvasProps {
  graph: GraphResponse | null;
  filterType: string;
  searchQuery: string;
  selectedId: string | null;
  onSelect: (nodeId: string) => void;
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

function GraphNodeCard({ data, selected }: NodeProps<Node<NodePayload>>) {
  return (
    <div className={`graph-node graph-node--${data.kind} ${selected ? 'is-selected' : ''}`}>
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

function CanvasInner({ graph, filterType, searchQuery, selectedId, onSelect }: GraphCanvasProps) {
  const { fitView } = useReactFlow();
  const visibleRawNodes = useMemo(
    () => pickVisibleNodes(graph?.nodes ?? [], filterType, searchQuery),
    [filterType, graph?.nodes, searchQuery],
  );
  const flowNodes = useMemo(() => {
    const positions = createGraphPositions(visibleRawNodes);
    return visibleRawNodes.map((node): Node<NodePayload> => ({
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
      },
    }));
  }, [selectedId, visibleRawNodes]);
  const ids = useMemo(() => new Set(flowNodes.map((node) => node.id)), [flowNodes]);
  const flowEdges = useMemo(() => {
    const rows = (graph?.edges ?? []).filter((edge) => ids.has(edge.source) && ids.has(edge.target));
    return rows.slice(0, 1400).map((edge: GraphEdge): Edge => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.type,
      type: 'smoothstep',
      animated: false,
      style: edge.provenance_type === 'inferred'
        ? { stroke: '#bd9bf5', strokeDasharray: '5 4', strokeWidth: 1.5 }
        : { stroke: '#536878', strokeWidth: 1.35 },
      labelStyle: { fill: '#9cafbd', fontSize: 10, fontWeight: 500 },
      labelBgStyle: { fill: '#111b24', fillOpacity: 0.94 },
      labelBgPadding: [4, 2] as [number, number],
    }));
  }, [graph?.edges, ids]);

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
    <ReactFlow
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
          const payload = node.data as NodePayload;
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
        <span>{flowNodes.length} de {graph.total_nodes || graph.nodes.length} nós · use busca ou filtros para explorar os detalhes</span>
      </div>
    )}
    {(filterType !== 'all' || searchQuery.trim()) && (
      <div className="canvas-view-note canvas-view-note--filtered" role="status">
        <strong>EXPLORAÇÃO FILTRADA</strong>
        <span>{flowNodes.length} de {graph.total_nodes} nó(s) correspondentes nesta busca/filtro{graph.total_nodes > flowNodes.length && flowNodes.length >= 500 ? ' · limite visual de 500 nós' : ''}</span>
      </div>
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
