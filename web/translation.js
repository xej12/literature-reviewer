/* Manual selection translation. Selection alone never calls the model. */
let selectedTranslation = null;
let translationRequest = 0;
let cardSaveInFlight = false;
document.body.insertAdjacentHTML('beforeend', `
  <button id="selection-translate" class="primary-button" hidden>译 · 翻译</button>
  <button id="selection-save-note" class="secondary-button" hidden>存入笔记</button>
  <button id="selection-save-card" class="secondary-button" hidden>存入卡片</button>
  <p id="selection-card-status" role="status" aria-live="polite" hidden></p>
  <aside id="selection-note-menu" hidden aria-label="保存选段到笔记">
    <div class="selection-note-head"><strong>保存选段到笔记</strong><button id="selection-note-close" class="close-button" aria-label="关闭保存选段">×</button></div>
    <p id="selection-note-preview"></p><div id="selection-note-options"></div><p id="selection-note-status" role="status"></p>
  </aside>
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
  $('#selection-save-note').hidden = true;
  $('#selection-save-card').hidden = true;
  $('#selection-card-status').hidden = true;
  $('#selection-note-menu').hidden = true;
  $('#translation-panel').hidden = true;
  document.body.classList.remove('translation-open');
  translationRequest++;
}

function selectedNoteBody(selection) {
  const text = String(selection.text || '').trim().replace(/\n/g, '\n> ');
  const heading = String(selection.heading || '论文深度解读').trim();
  const source = selection.page ? `PDF 第 ${selection.page} 页` : '论文解读正文';
  return `## 划词摘录：${heading}\n\n> ${text}\n\n> 来源：${source}`;
}

async function openSelectionNoteMenu() {
  if (!selectedTranslation) return;
  $('#selection-translate').hidden = true;
  $('#selection-save-note').hidden = true;
  $('#selection-save-card').hidden = true;
  $('#selection-card-status').hidden = true;
  const menu = $('#selection-note-menu'), preview = $('#selection-note-preview'), options = $('#selection-note-options'), status = $('#selection-note-status');
  menu.hidden = false; status.textContent = '正在读取当前文献的笔记…'; options.innerHTML = '';
  preview.textContent = selectedTranslation.text;
  const rect = selectedTranslation.rect;
  menu.style.left = `${Math.max(8, Math.min(rect.left, innerWidth - 330))}px`;
  menu.style.top = `${Math.max(8, Math.min(rect.bottom + 8, innerHeight - 220))}px`;
  try {
    const result = await getJson(`/api/notes?itemKey=${encodeURIComponent(selectedTranslation.itemKey)}`);
    const entries = result.notes.slice(0, 30);
    options.innerHTML = `<button type="button" class="primary-button selection-note-action" data-action="new">新建空白笔记</button>${entries.length ? `<span>或追加到已有笔记：</span>${entries.map(note => `<button type="button" class="text-button selection-note-action" data-note-id="${note.id}">${escapeHtml(note.title)}</button>`).join('')}` : ''}`;
    status.textContent = entries.length ? '选择保存位置；不会调用模型。' : '新建一篇笔记保存选段；不会调用模型。';
    options.querySelectorAll('.selection-note-action').forEach(button => button.onclick = () => saveSelectionToNote(button, status));
  } catch (error) { status.textContent = `读取笔记失败：${error.message}`; }
}

async function saveSelectionToNote(button, status) {
  if (button.dataset.saved === 'true' || button.dataset.saving === 'true') return;
  button.dataset.saving = 'true';
  button.disabled = true;
  button.style.cursor = 'wait';
  status.textContent = '正在保存…';
  try {
    const note = button.dataset.action === 'new'
      ? await postJson('/api/notes', {template:'blank', itemKey:selectedTranslation.itemKey})
      : await getJson(`/api/notes/${button.dataset.noteId}`);
    const excerpt = selectedNoteBody(selectedTranslation);
    if (note.body.includes(excerpt)) {
      status.textContent = '这段内容已经在该笔记中。';
      button.textContent = '已保存';
      button.dataset.saved = 'true';
      return;
    }
    const body = `${note.body.trimEnd()}${note.body.trim() ? '\n\n---\n\n' : ''}${excerpt}\n`;
    const saved = await postJson(`/api/notes/${note.id}`, {title:note.title, body, revision:note.revision});
    status.textContent = `已保存到「${saved.title}」`;
    button.textContent = '已保存';
    button.dataset.saved = 'true';
    if (window.notesWorkspace?.refresh) window.notesWorkspace.refresh().catch(() => {});
  } catch (error) {
    status.textContent = `保存失败：${error.message}`;
    button.disabled = false;
    button.style.cursor = 'pointer';
  } finally {
    button.dataset.saving = 'false';
    button.disabled = false;
    button.style.cursor = 'pointer';
  }
}

async function saveSelectionCard() {
  if (!selectedTranslation || cardSaveInFlight) return;
  const button = $('#selection-save-card');
  if (button.dataset.saved === 'true') return;
  const status = $('#selection-card-status');
  cardSaveInFlight = true;
  button.disabled = true;
  button.textContent = '正在保存…';
  status.className = 'selection-card-status is-loading';
  status.textContent = '正在保存到“我的卡片”，请稍候…';
  status.hidden = false;
  const text=selectedTranslation.text.trim();
  try {
    const source=`${selectedTranslation.heading || '论文解读正文'}${selectedTranslation.page ? ` · PDF 第 ${selectedTranslation.page} 页` : ''}`;
    await postJson('/api/cards',{title:`${selectedTranslation.heading || '阅读摘录'} · ${text.replace(/\s+/g,' ').slice(0,45)}`,content:text,source,itemKey:selectedTranslation.itemKey});
    button.textContent = '已存入卡片';
    button.disabled = false;
    button.dataset.saved = 'true';
    button.style.cursor = 'default';
    status.className = 'selection-card-status is-success';
    status.textContent = '已成功保存到“我的卡片”。';
    // Refreshing the sidebar is best-effort and must not mask a successful save.
    if (window.notesWorkspace?.refresh) window.notesWorkspace.refresh().catch(() => {});
  } catch (error) {
    button.disabled = false;
    button.textContent = '存入卡片';
    button.style.cursor = 'pointer';
    status.className = 'selection-card-status is-error';
    status.textContent = `保存失败：${error.message || String(error)}`;
    status.hidden = false;
  } finally {
    cardSaveInFlight = false;
  }
}

function captureTranslationSelection() {
  const selection = window.getSelection();
  const text = selection?.toString().trim();
  const button = $('#selection-translate');
  button.hidden = true;
  $('#selection-save-note').hidden = true;
  $('#selection-save-card').hidden = true;
  $('#selection-card-status').hidden = true;
  if (!state.selected || !text || text.length > 2000 || !selection.rangeCount) return;
  const range = selection.getRangeAt(0);
  const element = range.commonAncestorContainer.nodeType === 1 ? range.commonAncestorContainer : range.commonAncestorContainer.parentElement;
  if (!element || element.closest('[hidden], .hidden, #translation-panel, #terminology-modal, input, textarea, button, select, .katex')) return;
  if (!element.closest('#detail, #analysis-modal-body, #selection-pdf-page')) return;
  const paragraph = element.closest('p, blockquote, .deep-prose, h2, h3, .abstract') || element;
  const surrounding = paragraph.textContent || text;
  const position = surrounding.indexOf(text);
  const start = Math.max(0, position - 1500);
  selectedTranslation = {itemKey: state.selected.key, text, context: surrounding.slice(start, start + 6000), heading: element.closest('.deep-block')?.querySelector('h4')?.textContent || element.closest('.deep-chapter-heading')?.querySelector('h3')?.textContent || '论文深度解读'};
  if (element.closest('#selection-pdf-page') && window.selectionPdfView) {
    selectedTranslation.attachmentKey = selectionPdfView.pdf.key;
    selectedTranslation.page = selectionPdfView.page;
  }
  const rect = range.getBoundingClientRect();
  selectedTranslation.rect = rect;
  button.hidden = false;
  button.style.left = `${Math.max(8, Math.min(rect.left, innerWidth - button.offsetWidth - 8))}px`;
  button.style.top = `${Math.max(8, Math.min(rect.bottom + 7, innerHeight - button.offsetHeight - 8))}px`;
  const saveButton = $('#selection-save-note');
  saveButton.hidden = false;
  saveButton.style.left = `${Math.max(8, Math.min(rect.left, innerWidth - saveButton.offsetWidth - 8))}px`;
  saveButton.style.top = `${Math.max(8, Math.min(rect.bottom + button.offsetHeight + 14, innerHeight - saveButton.offsetHeight - 8))}px`;
  const cardButton=$('#selection-save-card');
  cardButton.hidden=false;
  cardSaveInFlight = false;
  cardButton.dataset.saved = 'false';
  cardButton.style.cursor = 'pointer';
  const cardStatus = $('#selection-card-status');
  cardStatus.hidden = true;
  cardStatus.className = 'selection-card-status';
  cardStatus.style.left = `${Math.max(8, Math.min(rect.left, innerWidth - 290))}px`;
  cardStatus.style.top = `${Math.max(8, Math.min(rect.bottom + 3 * (button.offsetHeight + 7), innerHeight - 52))}px`;
  cardButton.style.left=`${Math.max(8, Math.min(rect.left, innerWidth - cardButton.offsetWidth - 8))}px`;
  cardButton.style.top=`${Math.max(8, Math.min(rect.bottom + 2 * (button.offsetHeight + 7), innerHeight - cardButton.offsetHeight - 8))}px`;
}

async function runSelectionTranslation(selection = selectedTranslation, force = false) {
  if (!selection) return;
  const request = ++translationRequest;
  $('#selection-translate').hidden = true;
  $('#selection-save-note').hidden = true;
  $('#selection-save-card').hidden = true;
  $('#selection-card-status').hidden = true;
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
  $('#selection-save-note').hidden = true;
  $('#selection-save-card').hidden = true;
  $('#selection-card-status').hidden = true;
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
$('#selection-save-note').addEventListener('pointerdown', event=>event.preventDefault());
$('#selection-save-card').addEventListener('pointerdown', event=>event.preventDefault());
$('#selection-translate').addEventListener('click', ()=>runSelectionTranslation());
$('#selection-save-note').addEventListener('click', openSelectionNoteMenu);
$('#selection-save-card').addEventListener('click', saveSelectionCard);
$('#translation-close').onclick = dismissSelectionTranslation;
$('#selection-note-close').onclick = ()=>$('#selection-note-menu').hidden = true;
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
document.addEventListener('mouseup', event=>{if(!event.target.closest('#selection-translate, #selection-save-note, #selection-save-card, #selection-note-menu, #translation-panel, #terminology-modal')) captureTranslationSelection();});
document.addEventListener('keyup', event=>{if(event.key==='Shift') captureTranslationSelection();});
let translationSelectionTimer;
document.addEventListener('selectionchange', ()=>{
  clearTimeout(translationSelectionTimer);
  if(!window.getSelection()?.toString().trim()) { $('#selection-translate').hidden=true; $('#selection-save-note').hidden=true; $('#selection-save-card').hidden=true; $('#selection-card-status').hidden=true; }
  else translationSelectionTimer=setTimeout(captureTranslationSelection,200);
});
document.addEventListener('scroll', ()=>{ $('#selection-translate').hidden=true; $('#selection-save-note').hidden=true; $('#selection-save-card').hidden=true; $('#selection-card-status').hidden=true; $('#selection-note-menu').hidden=true; },true);
window.addEventListener('hashchange', dismissSelectionTranslation);
document.addEventListener('keydown', event=>{
  if(event.key==='Escape') {
    if(!$('#terminology-modal').classList.contains('hidden')) $('#terminology-modal').classList.add('hidden');
    else dismissSelectionTranslation();
  }
});
