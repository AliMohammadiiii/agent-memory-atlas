import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { chooseGraphNodes, visibleEdges } from '../src/graphLogic.js';
import { capabilityCell, licenseWithheld } from '../src/evidenceLogic.js';

const base = new URL('../fixtures/synthetic-react/', import.meta.url);
const read = path => JSON.parse(readFileSync(new URL(path, base), 'utf8'));

test('synthetic snapshot feeds React search, graph, page evidence and export', () => {
  const manifest = read('manifest.json');
  assert.match(manifest.atlas.title, /SYNTHETIC/);
  const papers = read(manifest.files.index);
  const rows = Array.isArray(papers) ? papers : papers.papers;
  const filtered = rows.filter(p => p.title.toLowerCase().includes('episodic'));
  assert.deepEqual(filtered.map(p => p.id), ['SYN-001']);
  const graph = read(manifest.files.graph);
  const selected = chooseGraphNodes(graph.nodes, {query:'SYN-001', selected:'SYN-001'});
  assert.ok(selected.nodes.some(n => n.id === 'SYN-001'));
  const edges = visibleEdges(graph.edges, graph.nodes, 'citation', ['citation']);
  assert.ok(edges.some(e => e.source === 'SYN-001' && e.target === 'SYN-002'));
  const matrix = read(manifest.files.matrix);
  const cell = capabilityCell(matrix.rows, 'SYN-001', 'synthetic');
  assert.equal(cell.location, 'PDF p. 2');
  assert.match(cell.quote, /Episodic retrieval/);
  assert.equal(licenseWithheld(cell), false);
  const csl = read(manifest.files.exports.csl);
  assert.ok(csl.some(row => row.id === 'SYN-001'));
});
