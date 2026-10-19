const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const root = path.resolve(__dirname, '..'), elements = new Map();
function $(id) {
  if (!elements.has(id)) {
    const classes = new Set(id === '#research-preview' ? ['hidden'] : []);
    elements.set(id, {value: '', textContent: '', innerHTML: '', disabled: false,
      classList: {add: c => classes.add(c), remove: c => classes.delete(c), contains: c => classes.has(c),
        toggle(c, on) { if(on) classes.add(c); else classes.delete(c); }},
      querySelectorAll: () => [], scrollIntoView() {}, focus() {}});
  }
  return elements.get(id);
}
let calls = [], cancels = [], pending;
const state = {selected: {key: 'PAPER', title: '<img src=x onerror=alert(1)>'}, demo: false, research: {goal: ''}};
const context = { $, state, window: {addEventListener() {}}, document: {addEventListener() {}},
  AbortController, crypto: require('node:crypto').webcrypto, setTimeout, clearTimeout,
  escapeHtml: value => String(value).replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;'),
  getJson: async () => ({total: 0, items: []}),
  postJson: (url, body, options) => {calls.push({url, body, options}); return new Promise(resolve => {pending = resolve;});},
  fetch: async url => {cancels.push(url); return {ok: true};}, showError: e => {throw e;}};
vm.createContext(context);
for (const file of ['reading.js', 'research-suggestions.js']) vm.runInContext(fs.readFileSync(path.join(root, 'web', file), 'utf8'), context);
const result = {goal: 'A suggested topic', topics: 'A | B', reason: 'Titles and abstracts only', papers: [{hasAbstract: true}]};
(async () => {
  context.initResearchSuggestion();
  context.resetResearchSuggestion();
  await Promise.resolve();
  assert.equal(calls.length, 0, 'opening/selecting papers is free');
  assert.ok(!$('#research-selected').innerHTML.includes('<img'));
  assert.match(context.paperPriority({}), /id="evaluate-priority"[^>]*disabled/);
  $('#research-goal').value = 'My unsaved draft';
  const cancelled = context.generateResearchSuggestion();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/research/suggest');
  assert.deepEqual(Array.from(calls[0].body.keys), ['PAPER']);
  context.stopResearchSuggestion();
  assert.ok(calls[0].options.signal.aborted);
  assert.match(cancels[0], /^\/api\/generations\/[a-f0-9]{32}\/cancel$/);
  pending(result); await cancelled;
  assert.equal($('#research-goal').value, 'My unsaved draft');
  assert.ok($('#research-preview').classList.contains('hidden'), 'ignore late responses after cancellation');
  const accepted = context.generateResearchSuggestion();
  pending(result); await accepted;
  assert.equal(calls.length, 2, 'never automatically retry');
  assert.equal($('#research-preview-goal').textContent, result.goal);
  assert.equal($('#research-goal').value, 'My unsaved draft', 'generation must not overwrite a draft');
  $('#research-adopt').onclick();
  assert.equal($('#research-goal').value, result.goal);
  assert.equal(state.research.goal, '', 'adoption must not save a profile');
  assert.ok(calls.every(c => c.url !== '/api/research'));
  console.log('Research preview, explicit adoption, no automatic save/retry and cancellation checks passed; paid model calls: 0.');
})().catch(error => {console.error(error); process.exitCode = 1;});
