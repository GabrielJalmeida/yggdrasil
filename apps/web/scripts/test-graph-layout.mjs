import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const ts = require('typescript');
const sourcePath = resolve(here, '../src/lib/graphLayout.ts');
const source = readFileSync(sourcePath, 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, strict: true },
}).outputText;
const loaded = { exports: {} };
new Function('exports', 'require', 'module', compiled)(loaded.exports, require, loaded);
const { createGraphPositions, pickVisibleNodes } = loaded.exports;

const kinds = [
  'repository', 'directory', 'file', 'module', 'configuration', 'dependency',
  'endpoint', 'class', 'model', 'function', 'method', 'test', 'skill', 'finding',
];
const nodes = Array.from({ length: 420 }, (_, index) => {
  const type = kinds[(index * 7 + Math.floor(index / 3)) % kinds.length];
  return {
    id: `node-${index}`,
    type,
    stable_key: `${type}:${index}`,
    label: `symbol-${index}`,
    path: `src/area-${index % 17}/file-${index % 61}.py`,
    start_line: index + 1,
    end_line: index + 1,
    properties: {},
    provenance_type: 'deterministic',
  };
});

const positions = createGraphPositions(nodes);
assert.equal(positions.size, nodes.length, 'every node must get a position');
const boxes = nodes.map((node) => ({ node, ...positions.get(node.id) }));
const width = 190;
const height = 75;
for (let i = 0; i < boxes.length; i += 1) {
  for (let j = i + 1; j < boxes.length; j += 1) {
    const a = boxes[i];
    const b = boxes[j];
    const overlaps = a.x < b.x + width && a.x + width > b.x
      && a.y < b.y + height && a.y + height > b.y;
    assert.equal(overlaps, false, `nodes ${a.node.id} and ${b.node.id} overlap`);
  }
}

const repeatedPositions = createGraphPositions([...nodes].reverse());
for (const node of nodes) {
  assert.deepEqual(repeatedPositions.get(node.id), positions.get(node.id), 'layout must be independent of input order');
}

const overview = pickVisibleNodes(nodes, 'all', '');
assert.ok(overview.length <= 180, `overview must have at most 180 nodes, got ${overview.length}`);
assert.ok(overview.length > 0, 'overview should not be empty');
const overviewIds = new Set(overview.map((node) => node.id));
const hiddenTraceNode = nodes.find((node) => !overviewIds.has(node.id));
assert.ok(hiddenTraceNode, 'fixture needs a node outside the summarized overview');
const tracedOverview = pickVisibleNodes(nodes, 'all', '', 0, [hiddenTraceNode.id]);
assert.ok(tracedOverview.some((node) => node.id === hiddenTraceNode.id), 'evidence highlights must surface traced nodes in overview mode');
const filteredTrace = pickVisibleNodes(nodes, 'function', 'never-match', 0, [hiddenTraceNode.id]);
assert.ok(!filteredTrace.some((node) => node.id === hiddenTraceNode.id), 'trace highlights must not bypass active search/type filters');
const filtered = pickVisibleNodes(nodes, 'module', '');
assert.ok(filtered.length <= 500, 'filtered view must respect the visual cap');
assert.ok(filtered.every((node) => node.type === 'module'), 'type filter must only return matching nodes');
const largeSearchNodes = Array.from({ length: 1200 }, (_, index) => ({
  id: `paged-${index}`, type: 'function', stable_key: `function:paged-${index}`,
  label: `calculate_${index}`, path: `src/paged_${index}.py`, start_line: 1, end_line: 1,
  properties: {}, provenance_type: 'deterministic',
}));
const firstPage = pickVisibleNodes(largeSearchNodes, 'function', 'calculate');
const secondPage = pickVisibleNodes(largeSearchNodes, 'function', 'calculate', 500);
assert.equal(firstPage.length, 500, 'first filtered page should contain 500 nodes');
assert.equal(secondPage.length, 500, 'second filtered page should contain 500 nodes');
assert.notEqual(firstPage[0].id, secondPage[0].id, 'visual pages must not repeat the same nodes');
const searched = pickVisibleNodes(nodes, 'all', 'symbol-42');
assert.ok(searched.length > 0 && searched.every((node) => `${node.label} ${node.path} ${node.stable_key}`.toLowerCase().includes('symbol-42')));

console.log(`Graph layout OK: ${nodes.length} nodes, no overlaps; overview=${overview.length}; filtered modules=${filtered.length}.`);
