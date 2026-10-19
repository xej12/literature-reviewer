// Suggestions are drafts. Only the existing explicit profile save writes a goal.
const researchSuggestion = { selected: [], epoch: 0, pickerRequest: 0, job: null, draft: null, timer: null };

function renderResearchSelection() {
  const r = researchSuggestion;
  $('#research-selected-count').textContent = `已选 ${r.selected.length} / 5 篇`;
  $('#research-selected').innerHTML = r.selected.map(p => `<li><span>${escapeHtml(p.title)}</span><button class="text-button" data-remove="${escapeHtml(p.key)}" aria-label="移除 ${escapeHtml(p.title)}" ${r.job ? 'disabled' : ''}>移除</button></li>`).join('');
  $('#research-selected').querySelectorAll('[data-remove]').forEach(button => button.onclick = () => {
    r.selected = r.selected.filter(p => p.key !== button.dataset.remove);
    clearResearchPreview(); renderResearchSelection(); loadResearchPicker();
  });
  $('#research-suggest').disabled = !!r.job || !r.selected.length || state.demo;
  $('#research-suggest').textContent = r.draft ? '重新生成建议（消耗 Token）' : '生成建议（消耗 Token）';
  $('#research-picker-query').disabled = !!r.job;
  $('#research-stop').classList.toggle('hidden', !r.job);
}

function clearResearchPreview() {
  researchSuggestion.draft = null;
  $('#research-preview').classList.add('hidden');
}

async function loadResearchPicker() {
  const r = researchSuggestion, epoch = r.epoch, request = ++r.pickerRequest;
  $('#research-picker-status').textContent = '正在读取文献库…';
  try {
    const data = await getJson('/api/discovery/library?q=' + encodeURIComponent($('#research-picker-query').value.trim()));
    if (epoch !== r.epoch || request !== r.pickerRequest) return;
    $('#research-picker-status').textContent = `找到 ${data.total} 篇，显示前 ${data.items.length} 篇；可搜索缩小范围。`;
    $('#research-picker-list').innerHTML = data.items.map(p => `<button class="research-pick" data-key="${escapeHtml(p.key)}" ${r.job || r.selected.length >= 5 || r.selected.some(s => s.key === p.key) ? 'disabled' : ''}><span>${escapeHtml(p.title)}</span><small>${r.selected.some(s => s.key === p.key) ? '已选' : '＋ 选择'}</small></button>`).join('') || '<p>没有匹配的文献，请更换关键词。</p>';
    $('#research-picker-list').querySelectorAll('[data-key]').forEach(button => button.onclick = () => {
      if (r.job || r.selected.length >= 5) return;
      r.selected.push(data.items.find(p => p.key === button.dataset.key));
      clearResearchPreview(); renderResearchSelection(); loadResearchPicker();
    });
  } catch (error) {
    if (epoch === r.epoch && request === r.pickerRequest) $('#research-picker-status').textContent = error.message;
  }
}

function stopResearchSuggestion() {
  const r = researchSuggestion, job = r.job;
  r.epoch++; r.pickerRequest++; clearTimeout(r.timer);
  if (!job) return;
  r.job = null; job.controller.abort();
  fetch(`/api/generations/${job.id}/cancel`, { method: 'POST', keepalive: true }).then(response => {
    if (!response.ok) throw Error('停止生成未送达，请检查本电脑服务。');
  }).catch(showError);
  $('#research-suggestion-status').textContent = '已停止请求，未修改研究方向。停止前已产生的用量由模型服务计费。';
  $('#save-research').disabled = false;
  $('#research-adopt').disabled = false;
  renderResearchSelection();
  if (!$('#research-modal').classList.contains('hidden')) loadResearchPicker();
}

function resetResearchSuggestion() {
  const r = researchSuggestion;
  r.epoch++; r.selected = state.selected ? [{ key: state.selected.key, title: state.selected.title }] : [];
  clearResearchPreview();
  $('#research-adopt').disabled = false;
  $('#research-picker-query').value = '';
  $('#research-suggestion-status').textContent = state.demo ? '示例模式不调用模型。' : '';
  renderResearchSelection(); loadResearchPicker();
}

async function generateResearchSuggestion() {
  const r = researchSuggestion;
  if (r.job || !r.selected.length || state.demo) return;
  const epoch = r.epoch, job = { id: crypto.randomUUID().replaceAll('-', ''), controller: new AbortController() };
  r.job = job;
  renderResearchSelection();
  $('#research-picker-list').querySelectorAll('button').forEach(b => b.disabled = true);
  $('#save-research').disabled = true;
  $('#research-adopt').disabled = true;
  $('#research-suggestion-status').textContent = '正在根据所选论文的标题与摘要生成建议，编辑框和已保存目标保持原样…';
  try {
    const result = await postJson('/api/research/suggest', { keys: r.selected.map(p => p.key) }, {
      signal: job.controller.signal, headers: { 'X-Generation-ID': job.id }
    });
    if (epoch !== r.epoch || r.job !== job) return;
    r.draft = result;
    for (const field of ['goal', 'topics', 'reason']) $('#research-preview-' + field).textContent = result[field];
    $('#research-preview').classList.remove('hidden');
    const missing = result.papers.filter(p => !p.hasAbstract).length;
    $('#research-suggestion-status').textContent = `建议已生成，尚未采用或保存。${missing ? `${missing} 篇没有摘要，建议仅参考其标题。` : '依据所选标题和摘要，未读取全文。'}`;
    $('#research-preview').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (error) {
    if (epoch === r.epoch && r.job === job) $('#research-suggestion-status').textContent = error.message;
  } finally {
    if (r.job === job) {
      r.job = null;
      $('#save-research').disabled = false;
      $('#research-adopt').disabled = false;
      renderResearchSelection(); loadResearchPicker();
    }
  }
}

function initResearchSuggestion() {
  $('#research-picker-query').oninput = () => {
    clearTimeout(researchSuggestion.timer); researchSuggestion.pickerRequest++;
    researchSuggestion.timer = setTimeout(loadResearchPicker, 250);
  };
  $('#research-suggest').onclick = generateResearchSuggestion;
  $('#research-stop').onclick = stopResearchSuggestion;
  $('#research-adopt').onclick = () => {
    const draft = researchSuggestion.draft;
    if (!draft || researchSuggestion.job) return;
    $('#research-goal').value = draft.goal; $('#research-topics').value = draft.topics;
    $('#research-message').textContent = '建议已填入编辑框，可继续修改。点击“保存研究方向”才生效。';
    $('#research-goal').focus();
  };
  window.addEventListener('pagehide', stopResearchSuggestion);
}
