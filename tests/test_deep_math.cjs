// Local renderer tests. No browser, API credentials or model calls required.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const katex = require('../web/vendor/katex/katex.min.js');
const escapeHtml = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const context = vm.createContext({window:{katex}, katex, escapeHtml});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/deep-reading.js'), 'utf8'), context);
const render = (value, block, source) => context.renderDeepText(value, block, source);
for (const malformed of [String.raw`\[\nf_{\rm AO}(\theta)=S f_{\rm core}(\theta)+(1-S)f_{\rm halo}(\theta)\]`,
  String.raw`\[\nC_{\rm res}=C_{\rm fit}+C_{\rm temp}\]`, String.raw`$$\n\frac{a}{b}\n$$`]) {
  const html = render(malformed);
  assert.ok(html.includes('class="katex"'));
  assert.ok(!html.includes('deep-math-fallback'));
}
for (const valid of [String.raw`\nu`,String.raw`\nabla f`,String.raw`\ne 0`,String.raw`\ni x`,String.raw`\newcommand{\foo}{x}\foo`]) {
  const html = render(`$${valid}$`);
  assert.ok(html.includes(katex.renderToString(valid, {displayMode:false,throwOnError:true,trust:false,strict:'ignore',maxExpand:1000})));
}
// A newline artifact elsewhere must not change valid nu in the same formula.
assert.ok(render(String.raw`$$\nu + \n \frac{1}{2}$$`).includes('annotation encoding="application/x-tex">\\nu +'));
assert.ok(render(String.raw`$$\nonsense{x}$$`).includes('deep-math-fallback'));
assert.ok(!render('<img src=x onerror=alert(1)>').includes('<img'));
assert.ok(!render(String.raw`$\href{https://example.invalid}{x}$`).includes('<a '));
const sources = [{page:2,text:'(3) A numbered list item\n(4) Another list item'}, {page:3,text:'Original formula (3)'},{page:4,text:'Original formula (4)'}];
const noteExcerpt = context.deepNoteExcerpt({title:'方法直觉', body:'先测量再校正。', basis:'paper', sources:[{page:3,text:'The field is measured.'}]}, {partial:true});
assert.ok(noteExcerpt.includes('## 深度解读摘录：方法直觉'));
assert.ok(noteExcerpt.includes('依据类型：论文原文'));
assert.ok(noteExcerpt.includes('第 3 页'));
assert.ok(noteExcerpt.includes('部分正文材料'));
const block = {basis:'paper',sources};
const coverage = {attachmentKey:'PDFKEY',pageCount:4};
const html = render('原文式（3）：\n$$f=x$$', block, coverage);
assert.ok(html.includes('data-page="3"'));
assert.ok(!html.includes('data-page="4"'));
assert.ok(!html.includes('data-page="2"'));
assert.ok(html.includes('data-src="/api/attachments/PDFKEY/page-image?page=3"'));
assert.ok(!html.includes('<img src=')); // Fetch originals only on explicit expansion.
assert.ok(render('$$f=x$$', block, coverage).includes('原式编号未明确'));
assert.ok(render('式(99)：$$f=x$$', block, coverage).includes('原文候选页'));
assert.ok(render('$$f=x$$', {basis:'background',sources}, coverage).includes('补充教学中的公式'));
assert.ok(!render('$$f=x$$', {basis:'background',sources}, coverage).includes('<details'));
assert.ok(!render('$$f=x$$', block, {attachmentKey:'" onclick="bad'}).includes('data-key='));
assert.ok(!render('$$f=x$$', {basis:'paper',sources:[{page:99,text:'(3)'}]},coverage).includes('data-page='));
const dense = '原文式(4)：$C_{res}(\\theta)\\propto |E|^2$，其中符号需要逐项理解。式(5)：$SNR=N_p/\\sqrt{N_s}$，这是另一个关系。可以支持的：曲线存在差异。不能支持的：差异一定来自某个原因。';
const readable = render(dense);
assert.equal((readable.match(/class="katex-display"/g)||[]).length,2);
assert.ok((readable.match(/class="reading-paragraph"/g)||[]).length>=4);
const qa = render('问1：坐标是什么？答：角距与对比度。问2：能判断因果吗？答：不能，仅能观察趋势。');
assert.equal((qa.match(/class="reading-qa"/g)||[]).length,2);
assert.equal((qa.match(/class="reading-answer"/g)||[]).length,2);
assert.ok(qa.includes('角距与对比度。'));
assert.ok(render('- 横坐标：角距\n- 纵坐标：对比度').includes('<ul class="reading-list">'));
assert.ok(render('一段话。'.repeat(70)).split('reading-paragraph').length>2);
console.log('Formula rendering, original-page navigation and safe fallbacks passed; model calls: 0.');
