/* Only an explicit Install click can stage program replacement. */
(() => {
  let info = null, timer = null, running = false, transaction = null, failures = 0, previousFocus = null;
  const modal = document.querySelector('#update-modal');
  const element = id => document.querySelector('#update-' + id);
  const visible = () => !modal.classList.contains('hidden');
  const error = text => { element('error').textContent = text; element('error').classList.toggle('hidden', !text); };
  function paint(value) {
    info = value;
    element('current').textContent = 'v' + value.currentVersion;
    element('latest').textContent = value.latestVersion ? '最新正式版 v' + value.latestVersion : '';
    element('reason').textContent = value.reason || '';
    element('reason').classList.toggle('hidden', !value.reason);
    element('release-link').href = value.releaseUrl;
    element('notes').textContent = value.notes || '';
    element('notes-wrap').classList.toggle('hidden', !value.notes);
    document.querySelector('#update-dot').hidden = !value.available;
    const operation = value.operation || {};
    running = Boolean(value.busy);
    const ours = transaction && transaction === operation.id;
    let message = value.checking ? '正在向 GitHub 检查新版…' : value.checkError || (value.available ? `发现新版 v${value.latestVersion}。准备好后点击“立即更新”。` : value.latestVersion ? '当前已是最新版本。' : '点击“检查更新”获取最新版本。');
    if (running || ours || ['failed', 'rolled_back', 'recovery_failed', 'completed'].includes(operation.phase)) message = operation.message || message;
    if (value.currentVersion !== value.latestVersion && value.latestVersion && !value.available && !ours && !running) message = '当前使用的版本比最新公开发行版更新。';
    element('status').textContent = message;
    const downloading = running && operation.phase === 'downloading';
    element('progress').classList.toggle('hidden', !downloading);
    if (downloading) {
      const percent = operation.total ? Math.min(100, Math.round((operation.received || 0) * 100 / operation.total)) : 0;
      if (operation.total) element('progress').value = percent;
      else element('progress').removeAttribute('value');
      element('status').textContent = `${operation.message} ${operation.total ? percent + '%' : ((operation.received || 0) / 1048576).toFixed(1) + ' MB'}`;
    }
    modal.setAttribute('aria-busy', String(running));
    document.querySelector('#check-update').disabled = running || value.checking;
    document.querySelector('#install-update').classList.toggle('hidden', !value.available || !value.supported || running);
    document.querySelector('#install-update').disabled = value.checking;
    document.querySelector('#close-update').disabled = running;
    const complete = ours && operation.phase === 'completed' && value.currentVersion === operation.version;
    document.querySelector('#reload-update').classList.toggle('hidden', !complete);
    if (ours && ['failed','rolled_back','recovery_failed'].includes(operation.phase)) error(operation.message);
    if (complete) {
      transaction = null;
      // Flush happened before starting; no automatic model call or generation.
      location.reload();
      return;
    }
    if (running || value.checking) schedule(1000);
    else if (visible()) schedule(5000);
  }
  function schedule(delay) { clearTimeout(timer); timer = setTimeout(refresh, delay); }
  async function refresh() {
    try { const value = await getJson('/api/update'); failures = 0; paint(value); }
    catch (exception) {
      if (transaction || running) {
        failures++;
        element('status').textContent = '正在重新连接更新后的服务…';
        if (failures > 45) {
          error('服务尚未恢复连接。请保留运行窗口，查看提示；必要时重新双击 start.cmd，启动器会先尝试恢复旧程序。');
          document.querySelector('#close-update').disabled = false;
          running = false;
        }
        schedule(2000);
      } else if (visible()) error('无法连接本电脑服务：' + exception.message);
    }
  }
  async function request(path, payload) {
    if (!info) await refresh();
    return postJson('/api/update/' + path, payload, {headers:{'X-Update-Token':info.token}});
  }
  async function check(force = false) {
    error('');
    try { paint(await request('check', {force})); }
    catch (exception) { error(exception.message); }
  }
  async function install() {
    error('');
    const button = document.querySelector('#install-update'); button.disabled = true;
    try {
      if (analysisGeneration) throw Error('还有解读正在生成，请等生成结束后再更新。');
      if (document.querySelector('.modal:not(.hidden):not(#update-modal)')) throw Error('请先完成并关闭其他设置或阅读窗口，再更新程序。');
      if (typeof window.notesWorkspace?.flush === 'function' && !await window.notesWorkspace.flush()) throw Error('笔记尚未保存成功，请先保存笔记再更新。');
      const cardSummary = document.querySelector('#card-summary-input');
      if (cardSummary && cardSummary.value !== (cardSummary.dataset.savedSummary || '')) throw Error('卡片总结还有未保存的修改，请先点击“保存修改”再更新。');
      if (document.querySelector('#card-question')?.value.trim()) throw Error('卡片里还有未发送的问题，请先处理或暂存后再更新。');
      const value = await request('start', {version:info.latestVersion});
      transaction = value.operation.id;
      paint(value);
    } catch (exception) { error(exception.message); }
    finally { button.disabled = false; }
  }
  function close() {
    if (running) return;
    modal.classList.add('hidden'); clearTimeout(timer); previousFocus?.focus();
  }
  document.querySelector('#updates-button').onclick = async () => {
    previousFocus = document.activeElement; modal.classList.remove('hidden');
    document.querySelector('#close-update').focus(); error(''); await refresh();
  };
  document.querySelector('#close-update').onclick = close;
  document.querySelector('#check-update').onclick = () => check(true);
  document.querySelector('#install-update').onclick = install;
  document.querySelector('#reload-update').onclick = () => location.reload();
  modal.addEventListener('click', event => { if (event.target === modal) close(); });
  modal.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.stopPropagation(); close(); }
    if (event.key === 'Tab') {
      const list = [...modal.querySelectorAll('button:not(:disabled),a,summary')].filter(node => !node.closest('.hidden'));
      const first=list[0], last=list[list.length-1];
      if (event.shiftKey && document.activeElement===first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement===last) { event.preventDefault(); first?.focus(); }
    }
  });
  document.addEventListener('DOMContentLoaded', async () => {
    await refresh();
    if (info) await check(false); // Server caches automatic checks for 24 hours.
  }, {once:true});
})();
