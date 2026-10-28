import type { GraphNode } from './api';

const nodeCaps: Record<string, number> = {
  repository: 1,
  directory: 12,
  file: 20,
  module: 16,
  endpoint: 12,
  class: 10,
  model: 8,
  function: 20,
  method: 12,
  test: 10,
  dependency: 10,
  finding: 16,
  configuration: 6,
  skill: 5,
};

const nodeRank: Record<string, number> = {
  repository: 0,
  directory: 1,
  file: 2,
  module: 3,
  configuration: 3,
  dependency: 4,
  endpoint: 4,
  class: 5,
  model: 5,
  function: 5,
  method: 5,
  test: 5,
  skill: 6,
  finding: 6,
};

const OVERVIEW_NODE_LIMIT = 180;
const NODE_COLUMN_STEP = 235;
const NODE_ROW_STEP = 108;
const LAYER_GAP = 35;

function compareNodes(a: GraphNode, b: GraphNode): number {
  return (a.path ?? '').localeCompare(b.path ?? '')
    || a.type.localeCompare(b.type)
    || a.label.localeCompare(b.label)
    || a.stable_key.localeCompare(b.stable_key)
    || a.id.localeCompare(b.id);
}

/**
 * The initial canvas is an overview, not a dump of every symbol. Search and
 * type filters deliberately switch to a more detailed view (up to 500 nodes).
 */
export function pickVisibleNodes(nodes: GraphNode[], filterType: string, query: string, pageOffset = 0, highlightedNodeIds: string[] = []): GraphNode[] {
  const orderedNodes = [...nodes].sort(compareNodes);
  const needle = query.trim().toLowerCase();
  if (filterType !== 'all' || needle) {
    return orderedNodes.filter((node) => {
      const typeMatches = filterType === 'all' || node.type === filterType;
      const textMatches = !needle || `${node.label} ${node.path ?? ''} ${node.stable_key}`.toLowerCase().includes(needle);
      return typeMatches && textMatches;
    }).slice(Math.max(0, pageOffset), Math.max(0, pageOffset) + 500);
  }

  const grouped = new Map<string, GraphNode[]>();
  for (const node of orderedNodes) {
    const group = grouped.get(node.type);
    if (group) group.push(node);
    else grouped.set(node.type, [node]);
  }

  const selected: GraphNode[] = [];
  const selectedIds = new Set<string>();
  for (const [type, cap] of Object.entries(nodeCaps)) {
    for (const node of (grouped.get(type) ?? []).slice(0, cap)) {
      selected.push(node);
      selectedIds.add(node.id);
    }
  }

  // Top up to a hard overview budget instead of accidentally filling the
  // canvas with hundreds of extra files/functions.
  const contextTypes = new Set(['directory', 'file', 'module', 'function', 'endpoint', 'finding']);
  for (const node of orderedNodes) {
    if (selected.length >= OVERVIEW_NODE_LIMIT) break;
    if (!selectedIds.has(node.id) && contextTypes.has(node.type)) {
      selected.push(node);
      selectedIds.add(node.id);
    }
  }

  // In overview mode, include evidence/scan nodes even when they are beyond the
  // summary caps. Filters still remain strict and do not silently inject unrelated nodes.
  if (filterType === 'all' && !query.trim()) {
    const highlighted = new Set(highlightedNodeIds);
    for (const node of orderedNodes) {
      if (highlighted.has(node.id) && !selectedIds.has(node.id)) {
        selected.push(node);
        selectedIds.add(node.id);
      }
    }
  }

  return selected.sort(compareNodes);
}

/**
 * Deterministic, collision-free layered grid.
 * Each semantic rank receives its own vertical band sized from the actual
 * number of rows in that band. The previous fixed rank offset overlapped once
 * a busy rank (especially functions/methods) grew beyond one or two rows.
 */
export function createGraphPositions(nodes: GraphNode[]): Map<string, { x: number; y: number }> {
  const grouped = new Map<number, GraphNode[]>();
  for (const node of [...nodes].sort((a, b) => {
    const rankDelta = (nodeRank[a.type] ?? 4) - (nodeRank[b.type] ?? 4);
    return rankDelta || compareNodes(a, b);
  })) {
    const rank = nodeRank[node.type] ?? 4;
    const group = grouped.get(rank);
    if (group) group.push(node);
    else grouped.set(rank, [node]);
  }

  const positions = new Map<string, { x: number; y: number }>();
  let layerTop = 80;
  for (const rank of [...grouped.keys()].sort((a, b) => a - b)) {
    const group = grouped.get(rank) ?? [];
    // A slightly wider grid reduces the overall height without changing node size.
    const columns = Math.max(1, Math.ceil(Math.sqrt(group.length * 1.6)));
    const rows = Math.ceil(group.length / columns);

    group.forEach((node, index) => {
      const column = index % columns;
      const row = Math.floor(index / columns);
      positions.set(node.id, {
        x: 100 + column * NODE_COLUMN_STEP,
        y: layerTop + row * NODE_ROW_STEP,
      });
    });

    layerTop += rows * NODE_ROW_STEP + LAYER_GAP;
  }
  return positions;
}
