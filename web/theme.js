/* Run before styles and content to apply the saved appearance without a light flash.
   Native preference handling; no external scripts, requests or model calls. */
(() => {
  'use strict';
  const key = 'literature-reviewer.appearance';
  const choices = ['light', 'dark', 'system'];
  const labels = {light:'浅色', dark:'深色', system:'跟随系统'};
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  let preference = 'system';
  let canSave = true;
  let button, panel;

  function readPreference() {
    try {
      const saved = localStorage.getItem(key);
      return choices.includes(saved) ? saved : 'system';
    } catch { canSave = false; return 'system'; }
  }

  function apply() {
    const resolved = preference === 'system' ? (system.matches ? 'dark' : 'light') : preference;
    document.documentElement.dataset.theme = resolved;
    document.documentElement.dataset.appearance = preference;
    if (!button) return;
    document.getElementById('theme-label').textContent = labels[preference];
    const description = `外观主题：${labels[preference]}${preference === 'system' ? `（当前${labels[resolved]}）` : ''}`;
    button.setAttribute('aria-label', description);
    button.title = description;
    document.querySelectorAll('[data-theme-icon]').forEach(icon => {
      icon.toggleAttribute('hidden', icon.dataset.themeIcon !== preference);
    });
    panel.querySelectorAll('input[name="appearance"]').forEach(input => { input.checked = input.value === preference; });
    document.getElementById('theme-status').textContent = canSave
      ? `已使用${labels[resolved]} · 选择自动保存在此浏览器`
      : '已切换；此浏览器暂时无法记住选择';
  }

  preference = readPreference();
  apply();
  system.addEventListener('change', () => { if (preference === 'system') apply(); });
  window.addEventListener('storage', event => {
    if (event.key === key || event.key === null) { preference = readPreference(); apply(); }
  });

  document.addEventListener('DOMContentLoaded', () => {
    button = document.getElementById('theme-button');
    panel = document.getElementById('theme-panel');
    const picker = button.closest('.theme-picker');
    function close(returnFocus = false) {
      panel.hidden = true;
      button.setAttribute('aria-expanded', 'false');
      if (returnFocus) button.focus();
    }
    button.addEventListener('click', () => {
      panel.hidden = !panel.hidden;
      button.setAttribute('aria-expanded', String(!panel.hidden));
      if (!panel.hidden) panel.querySelector('input:checked').focus();
    });
    panel.addEventListener('change', event => {
      if (!event.target.matches('input[name="appearance"]') || !choices.includes(event.target.value)) return;
      preference = event.target.value;
      try { localStorage.setItem(key, preference); canSave = true; }
      catch { canSave = false; }
      apply();
    });
    picker.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !panel.hidden) { event.preventDefault(); close(true); }
    });
    picker.addEventListener('focusout', event => {
      // Clicking label text briefly blurs the radio before native label activation.
      // A null relatedTarget is not evidence that focus moved outside the picker.
      // Outside clicks are handled below; Tab closes on a real external target.
      if (event.relatedTarget && !picker.contains(event.relatedTarget)) close();
    });
    document.addEventListener('click', event => { if (!picker.contains(event.target)) close(); });
    apply();
  });
})();
