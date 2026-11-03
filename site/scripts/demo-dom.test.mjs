import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

class Element {
  constructor() { this.children = []; this.listeners = {}; this.style = {}; this.value = ''; this.textContent = ''; }
  addEventListener(type, fn) { this.listeners[type] = fn; }
  setAttribute(name, value) { this[name] = value; }
  append(child) { this.children.push(child); }
  replaceChildren() { this.children = []; this.textContent = ''; }
  click() { this.clicked = true; if (this.listeners.click) this.listeners.click(); }
}

test('standalone reviewer workflow filters, selects citation evidence, and exports displayed report', async () => {
  const report = {results: [{id:'SYN-001', page:2, score:1, text:'Episodic retrieval'}, {id:'SYN-002', page:3, score:0.8, text:'Index'}], fts_results:[{paper_id:'SYN-001',page:2,text:'Episodic retrieval'}], edges:[{source:'SYN-001',target:'SYN-002',type:'citation'}]};
  const elements = Object.fromEntries(['data','results','evidence','graph','fts','search','export'].map(id => [id, new Element()]));
  elements.data.textContent = JSON.stringify(report);
  let downloaded;
  const document = {getElementById: id => elements[id], createElement: tag => { const element = new Element(); if (tag === 'a') downloaded = element; return element; }};
  let exported;
  const urlApi = {createObjectURL: blob => { exported = blob; return 'blob:test'; }, revokeObjectURL: () => {}};
  const html = readFileSync(new URL('../../atlas_demo/report.html', import.meta.url), 'utf8');
  const source = html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
  runInNewContext(source, {document, URL: urlApi, Blob, setTimeout: fn => fn()});
  assert.equal(elements.results.children.length, 2);
  elements.search.value = 'index'; elements.search.listeners.input();
  assert.equal(elements.results.children.length, 1);
  elements.results.children[0].click();
  assert.match(elements.evidence.textContent, /SYN-002 · page 3/);
  elements.fts.children[0].click();
  assert.match(elements.evidence.textContent, /SYN-001 · page 2/);
  elements.graph.children[0].click();
  assert.match(elements.evidence.textContent, /SYN-001 · page 2/);
  elements.search.value = 'absent'; elements.search.listeners.input();
  assert.match(elements.results.textContent, /No matching/);
  elements.export.click();
  assert.equal(downloaded.download, 'atlas-synthetic-report.json');
  assert.equal(downloaded.clicked, true);
  assert.equal(exported.type, 'application/json');
  assert.deepEqual(JSON.parse(await exported.text()), report);
});
