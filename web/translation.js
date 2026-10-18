/* Manual selection translation. Selection alone never calls the model. */
let selectedTranslation = null;
let translationRequest = 0;
document.body.insertAdjacentHTML('beforeend', `
  <button id="selection-translate" class="primary-button" hidden>译 · 翻译</button>
  <aside id="translation-panel" hidden role="dialog" aria-modal="false" aria-labelledby="translation-title">
    <div class="translation-head"><div><small>CONTEXTUAL TRANSLATION</small><h2 id="translation-title">专业翻译</h2></div><button id="translation-close" class="close-button" aria-label="关闭翻译">×</button></div>
    <div id="translation-content" aria-live="polite"></div>
    <button id="translation-glossary" class="text-button">纠正译法 / 查看专业术语表</button>
    <button id="translation-term-lesson" class="secondary-button" hidden>结合本文打开术语精讲</button>
  </aside>
  <div id="terminology-modal" class="modal hidden" role="dialog" aria-modal="true" aria-labelledby="terminology-title">
    <div class="modal-card terminology-card"><div class="modal-head"><div><div class="eyebrow">PERSONAL GLOSSARY</div><h2 id="terminology-title">专业术语表</h2></div><button id="terminology-close" class="close-button" aria-label="关闭术语表">×</button></div>
    <p class="modal-intro">这里记录你认可的专业译法，供后续翻译、论文解读、术语与图表讲解共同使用。说明领域可避免一词多义；已有解读不会自动重新生成。</p>
    <form id="terminology-form"><label class="setting-field"><span>英文术语</span><input id="terminology-term" maxlength="150" required /></label><label class="setting-field"><span>专业中文译法</span><input id="terminology-chinese" maxlength="150" required /></label><label class="setting-field"><span>领域 / 含义说明</span><textarea id="terminology-note" maxlength="1000" rows="2"></textarea></label><button id="terminology-save" class="primary-button">保存译法（免费）</button></form>
    <p id="terminology-message" role="status"></p><div id="terminology-entries"></div></div>
  </div>`);

function dismissSelectionTranslation() {
  $('#selection-translate').hidden = true;
  $('#translation-panel').hidden = true;
  document.body.classList.remove('translation-open');
  translationRequest++;
}

function captureTranslationSelection() {
  const selection = window.getSelection();
  const text = selection?.toString().trim();
  const button = $('#selection-translate');
  button.hidden = true;
  if (!state.selected || !text || text.length > 2000 || !selection.rangeCount) return;
  const range = selection.getRangeAt(0);
  const element = range.commonAncestorContainer.nodeType === 1 ? range.commonAncestorContainer : range.commonAncestorContainer.parentElement;
  if (!element || element.closest('[hidden], .hidden, #translation-panel, #terminology-modal, input, textarea, button, select, .katex')) return;
  if (!element.closest('#detail, #analysis-modal-body, #selection-pdf-page')) return;
  const paragraph = element.closest('p, blockquote, .deep-prose, h2, h3, .abstract') || element;
  const surrounding = paragraph.textContent || text;
  const position = surrounding.indexOf(text);
  const start = Math.max(0, position - 1500);
  selectedTranslation = {itemKey: state.selected.key, text, context: surrounding.slice(start, start + 6000)};
  if (element.closest('#selection-pdf-page') && window.selectionPdfView) {
    selectedTranslation.attachmentKey = selectionPdfView.pdf.key;
    selectedTranslation.page = selectionPdfView.page;
  }
  const rect = range.getBoundingClientRect();
  button.hidden = false;
  button.style.left = `${Math.max(8, Math.min(rect.left, innerWidth - button.offsetWidth - 8))}px`;
  button.style.top = `${Math.max(8, Math.min(rect.bottom + 7, innerHeight - button.offsetHeight - 8))}px`;
}

async function runSelectionTranslation(selection = selectedTranslation, force = false) {
  if (!selection) return;
  const request = ++translationRequest;
  $('#selection-translate').hidden = true;
  $('#translation-panel').hidden = false;
  document.body.classList.add('translation-open');
  $('#translation-term-lesson').hidden = selection.text.length > 150;
  $('#translation-term-lesson').onclick = () => {
    if(state.selected?.key === selection.itemKey) {
      if(window.selectionPdfView) closeSelectionReader();
      openTermReading(state.selected, selection.text);
    }
  };
  const content = $('#translation-content');
  content.innerHTML = `<div class="translation-original"><small>原文</small><p>${escapeHtml(selection.text)}</p></div><p role="status">正在查询术语表与已存译文；需要时调用已配置模型…</p>`;
  try {
    const result = await postJson(`/api/items/${selection.itemKey}/translate`, {...selection, force});
    if (request !== translationRequest) return;
    content.innerHTML = `<div class="translation-original"><small>原文</small><p>${escapeHtml(selection.text)}</p></div><div class="translation-answer"><small>中文译文</small><p>${escapeHtml(result.translation)}</p></div>${result.explanation ? `<section><h3>专业含义 / 句意</h3><p>${escapeHtml(result.explanation)}</p></section>` : ''}${result.uncertainty ? `<p class="translation-caution">${escapeHtml(result.uncertainty)}</p>` : ''}${(result.notices || []).map(n=>`<p class="translation-caution">${escapeHtml(n)}</p>`).join('')}${result.terms?.length ? `<section><h3>采用的术语约定</h3>${result.terms.map(t=>`<p>${escapeHtml(t.term)} → ${escapeHtml(t.translation)}</p>`).join('')}</section>` : ''}<p class="translation-meta">${escapeHtml(result.source)} · ${result.method === 'glossary' ? '本地查询，不消耗 Token' : result.cached ? '已保存译文，不消耗 Token' : '已保存到当前文献'}</p>${result.method === 'model' ? `<button id="translation-retry" class="text-button">重新翻译（消耗 Token）</button>` : ''}`;
    $('#translation-retry')?.addEventListener('click', () => {
      if (confirm('重新翻译会调用模型并消耗 Token，继续吗？')) runSelectionTranslation(selection, true);
    });
  } catch (error) {
    if (request === translationRequest) content.insertAdjacentHTML('beforeend', `<p class="analysis-error" role="alert">${escapeHtml(error.message || String(error))}</p>`);
  }
}

async function openTerminology() {
  $('#selection-translate').hidden = true;
  $('#terminology-modal').classList.remove('hidden');
  $('#terminology-message').textContent = '正在读取本地术语表…';
  try {
    const data = await getJson('/api/terminology');
    paintTerminology(data);
    $('#terminology-message').textContent = '点击词条可修改译法。';
  } catch (error) { $('#terminology-message').textContent = error.message; }
}

function paintTerminology(data) {
  $('#terminology-entries').innerHTML = data.entries.map((e,i)=>`<button type="button" class="terminology-entry" data-entry="${i}"><strong>${escapeHtml(e.term)} <span>→ ${escapeHtml(e.translation)}</span></strong><small>${escapeHtml(e.note || '')}</small><em>${escapeHtml(e.source)}</em></button>`).join('');
  $('#terminology-entries').querySelectorAll('button').forEach(button=>button.onclick=()=>{
    const entry = data.entries[Number(button.dataset.entry)];
    $('#terminology-term').value = entry.term;
    $('#terminology-chinese').value = entry.translation;
    $('#terminology-note').value = entry.note || '';
    $('#terminology-term').focus();
  });
}

$('#selection-translate').addEventListener('pointerdown', event=>event.preventDefault());
$('#selection-translate').addEventListener('click', ()=>runSelectionTranslation());
$('#translation-close').onclick = dismissSelectionTranslation;
$('#translation-glossary').onclick = openTerminology;
$('#terminology-close').onclick = ()=>$('#terminology-modal').classList.add('hidden');
$('#terminology-modal').onclick = event=>{if(event.target.id==='terminology-modal') $('#terminology-modal').classList.add('hidden');};
$('#terminology-form').onsubmit = async event=>{
  event.preventDefault();
  const button = $('#terminology-save');button.disabled=true;
  try {
    const data = await postJson('/api/terminology', {term:$('#terminology-term').value,translation:$('#terminology-chinese').value,note:$('#terminology-note').value});
    paintTerminology(data);
    $('#terminology-message').textContent = '已保存，后续翻译和新生成的讲解会采用这个译法。';
  } catch(error) {$('#terminology-message').textContent=error.message;}
  finally {button.disabled=false;}
};
document.addEventListener('mouseup', event=>{if(!event.target.closest('#selection-translate, #translation-panel, #terminology-modal')) captureTranslationSelection();});
document.addEventListener('keyup', event=>{if(event.key==='Shift') captureTranslationSelection();});
let translationSelectionTimer;
document.addEventListener('selectionchange', ()=>{
  clearTimeout(translationSelectionTimer);
  if(!window.getSelection()?.toString().trim()) $('#selection-translate').hidden=true;
  else translationSelectionTimer=setTimeout(captureTranslationSelection,200);
});
document.addEventListener('scroll', ()=>{$('#selection-translate').hidden=true;},true);
window.addEventListener('hashchange', dismissSelectionTranslation);
document.addEventListener('keydown', event=>{
  if(event.key==='Escape') {
    if(!$('#terminology-modal').classList.contains('hidden')) $('#terminology-modal').classList.add('hidden');
    else dismissSelectionTranslation();
  }
});
