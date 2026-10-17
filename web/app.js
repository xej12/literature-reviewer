const state = { collection: "", query: "", items: [], selected: null, model: null, listScroll: 0, detailRequest: 0, progressFilter: "all", libraryRequest: 0, libraryLoading: false, lastSync: 0 };
const $ = (s) => document.querySelector(s);

function escapeHtml(value = "") {
  return String(value).replace(/[&<>'"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
}

function initials(item) {
  const text = item.creators?.[0] || item.title || "文";
  return text.trim().slice(0, 1).toUpperCase();
}

function authorSummary(creators = []) {
  if (!creators.length) return "作者信息未填写";
  return creators.length <= 3 ? creators.join(" · ") : `${creators.slice(0, 3).join(" · ")} 等 ${creators.length} 位`;
}

async function getJson(url) {
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok || payload.error) throw new Error(payload.error || `请求失败：${response.status}`);
  return payload;
}

async function postJson(url, body = {}) {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const payload = await response.json();
  if (!response.ok || payload.error) throw new Error(payload.error || `请求失败：${response.status}`);
  return payload;
}

function showError(error) {
  const box = $("#message");
  box.textContent = error.message || String(error);
  box.classList.remove("hidden");
}

function renderCollections(collections) {
  $("#all-count").textContent = state.allCount ?? "—";
  $("#collections").innerHTML = collections.map((c) => `
    <button class="collection" data-key="${escapeHtml(c.key)}"><span>${escapeHtml(c.name)}</span><strong>${c.itemCount}</strong></button>
  `).join("");
  $("#section-title").textContent = collections.find((c) => c.key === state.collection)?.name || "全部文献";
  document.querySelectorAll(".collection").forEach((button) => {
    button.classList.toggle("active", button.dataset.key === state.collection);
    button.onclick = () => {
      clearTimeout(searchTimer);
      state.collection = button.dataset.key;
      state.query = "";
      $("#search").value = "";
      loadItems();
    };
  });
}

const progressLabels = { all: "全部状态", summary: "已解读", unread: "未解读", terms: "已提取术语", figures: "已解析图表" };

function renderProgress(progress, matchingCount) {
  $("#progress-overview").classList.remove("hidden");
  for (const kind of ["summary", "unread", "terms", "figures"]) $("#progress-" + kind).textContent = progress[kind];
  const percent = progress.total ? Math.round(progress.summary / progress.total * 100) : 0;
  $("#summary-progress-fill").style.width = `${percent}%`;
  $("#summary-progress").setAttribute("aria-valuenow", String(percent));
  $("#summary-progress").setAttribute("aria-valuetext", `${progress.summary} / ${progress.total} 篇已有论文解读`);
  $("#progress-scope").textContent = `${$("#section-title").textContent}${state.query ? " · 当前搜索结果" : ""} · ${progress.total} 篇`;
  $("#progress-description").textContent = `${progress.summary} / ${progress.total} 篇已有论文解读（${percent}%） · 点击数字卡片筛选，查看已保存结果不消耗 Token`;
  document.querySelectorAll(".progress-card").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.status === state.progressFilter)));
  $("#clear-progress-filter").setAttribute("aria-pressed", String(state.progressFilter === "all"));
  $("#results-info").textContent = `${progressLabels[state.progressFilter]} · ${matchingCount} 篇${matchingCount > state.items.length ? `，当前显示前 ${state.items.length} 篇，可通过搜索缩小范围` : ""}`;
}

function analysisBadges(item) {
  const saved = item.analysisStatus || {};
  return `<div class="analysis-badges"><span class="analysis-badge ${saved.summary ? "done" : "pending"}">${saved.summary ? "解读已保存" : "未解读"}</span>${saved.terms ? `<span class="analysis-badge done">术语已保存</span>` : ""}${saved.figures ? `<span class="analysis-badge done">图表 ${saved.figureCount} 项</span>` : ""}</div>`;
}

function renderItems() {
  const target = $("#items");
  if (!state.items.length) {
    target.innerHTML = `<div class="no-results"><div>⌁</div><p>当前筛选下没有文献</p><small>可以点击“全部状态”、更换关键词或切换集合</small></div>`;
    return;
  }
  target.innerHTML = state.items.map((item) => `
    <button class="item-card ${state.selected?.key === item.key ? "selected" : ""}" data-key="${item.key}">
      <div class="item-mark">${escapeHtml(initials(item))}</div>
      <div class="item-main">
        <div class="item-type">${escapeHtml(item.itemType)} ${item.attachments?.some((attachment) => attachmentTypeLabel(attachment) === "PDF") ? "· PDF" : item.attachments?.length ? "· 附件" : ""}</div>
        <h3>${escapeHtml(item.title)}</h3>
        <p>${escapeHtml(authorSummary(item.creators))}</p>
        <div class="item-meta">${escapeHtml(item.publicationTitle || "")}${item.date ? ` · ${escapeHtml(item.date)}` : ""}</div>
        ${analysisBadges(item)}
      </div>
      <div class="arrow">›</div>
    </button>
  `).join("");
  document.querySelectorAll(".item-card").forEach((card) => card.addEventListener("click", () => selectItem(card.dataset.key)));
}

function renderDetail(item) {
  const detail = $("#detail");
  const pdf = item.attachments?.find((a) => attachmentTypeLabel(a) === "PDF" && a.exists);
  const openableAttachment = pdf || item.attachments?.find((a) => a.exists);
  const hasFigureCache = Boolean(pdf && Object.keys(item.analysis?.figures || {}).some((key) => key.startsWith(`${pdf.key}:`)));
  const attachmentLabel = openableAttachment ? (openableAttachment === pdf ? "打开 PDF ↗" : "打开附件 ↗") : "";
  detail.innerHTML = `
    <button id="close-detail" class="back-button">← 返回文献列表</button>
    <div class="detail-top"><span class="pill">${escapeHtml(item.itemType)}</span><span class="key">${escapeHtml(item.key)}</span></div>
    <h2 tabindex="-1">${escapeHtml(item.title)}</h2>
    <div id="paper-authors" class="detail-authors">${escapeHtml(authorSummary(item.creators))}</div>
    ${item.creators?.length > 3 ? `<button id="toggle-authors" class="text-button authors-toggle" aria-expanded="false" aria-controls="paper-authors">展开全部作者</button>` : ""}
    <dl class="facts">
      ${item.publicationTitle ? `<div><dt>期刊 / 来源</dt><dd>${escapeHtml(item.publicationTitle)}</dd></div>` : ""}
      ${item.date ? `<div><dt>日期</dt><dd>${escapeHtml(item.date)}</dd></div>` : ""}
      ${item.doi ? `<div><dt>DOI</dt><dd>${escapeHtml(item.doi)}</dd></div>` : ""}
      ${item.pages ? `<div><dt>页码</dt><dd>${escapeHtml(item.pages)}</dd></div>` : ""}
    </dl>
    <div class="detail-section"><div class="section-label">摘要</div><p class="abstract">${escapeHtml(item.abstract || "这篇文献没有记录摘要。")}</p></div>
    <div class="detail-section"><div class="section-label">附件</div>
      ${item.attachments?.length ? item.attachments.map(a => `<div class="attachment"><span class="pdf-icon">${escapeHtml(attachmentTypeLabel(a))}</span><span class="attachment-name">${escapeHtml(a.filename || "附件")}</span><em>${a.exists ? "已找到" : "未找到"}</em></div>`).join("") : `<p class="muted">暂无本地附件</p>`}
      ${!pdf ? `<p class="attachment-hint">${item.attachments?.some(a => attachmentTypeLabel(a) === "PDF") ? "PDF 文件未在本机找到，请在 Zotero 中确认附件已下载。" : "此条目没有 PDF 附件。网页快照和 PDF 是不同文件，可先打开来源网页阅读；在 Zotero 添加 PDF 后刷新即可。"}</p>` : ""}
      ${openableAttachment ? `<div class="reader-actions"><button id="read-attachment" class="primary-button">${attachmentLabel}</button>${item.url ? `<button id="open-source" class="text-button">打开来源网页 ↗</button>` : ""}</div>` : item.url ? `<div class="reader-actions"><button id="open-source" class="primary-button">打开来源网页 ↗</button></div>` : ""}
    </div>
    <div class="analysis-actions"><button id="analyze-summary" class="primary-button">${item.analysis?.summary ? "查看论文解读" : "生成论文解读"}</button><button id="extract-terms" class="secondary-button">${item.analysis?.terms ? "查看专业术语" : "提取专业术语"}</button>${pdf ? `<button id="analyze-figure" class="secondary-button">${hasFigureCache ? "查看图表解析" : "图表解析"}</button>` : ""}<span>${state.model?.configured ? `已配置：${escapeHtml(state.model.model)}` : "需配置模型"}</span></div>
    ${pdf ? `<div class="next-feature"><span>✦</span><div><strong>逐页理解</strong><br><small>可框选图表单独解析，结果会保存在当前文献下。</small></div></div>` : ""}
  `;
  $("#close-detail").addEventListener("click", closeDetail);
  $("#toggle-authors")?.addEventListener("click", (event) => {
    const authors = $("#paper-authors");
    const expanded = authors.classList.toggle("expanded");
    authors.textContent = expanded ? item.creators.join(" · ") : authorSummary(item.creators);
    event.currentTarget.textContent = expanded ? "收起作者" : "展开全部作者";
    event.currentTarget.setAttribute("aria-expanded", String(expanded));
  });
  $("#analyze-summary").addEventListener("click", () => analyzeSummary(item));
  $("#extract-terms").addEventListener("click", () => extractTerms(item));
  if (pdf) $("#analyze-figure").addEventListener("click", () => analyzeFigure(item, pdf));
  if (openableAttachment) $("#read-attachment").addEventListener("click", () => window.open(`/api/attachments/${openableAttachment.key}/file`, "_blank"));
  if (item.url) $("#open-source").addEventListener("click", () => window.open(item.url, "_blank", "noopener"));
}

function attachmentTypeLabel(attachment) {
  const name = String(attachment.filename || "").toLowerCase();
  if (attachment.contentType === "application/pdf" || name.endsWith(".pdf")) return "PDF";
  if (attachment.contentType === "text/html" || name.endsWith(".html") || name.endsWith(".htm")) return "网页";
  return "附件";
}

function closeDetail() {
  if (history.state?.paperFromLibrary) history.back();
  else {
    history.replaceState(null, "", "#/library");
    applyRoute();
  }
}

function openSettings() {
  getJson("/api/model").then((config) => {
    $("#setting-base-url").value = config.baseUrl || "";
    $("#setting-model").value = config.model || "";
    $("#setting-api-key").value = "";
    $("#settings-message").textContent = config.configured ? "当前已有可用配置。重新填写 API Key 可覆盖。" : "尚未配置模型。";
    $("#settings-modal").classList.remove("hidden");
  }).catch(showError);
}

function closeSettings() {
  $("#settings-modal").classList.add("hidden");
}

function openAnalysis(title, eyebrow = "PAPER ANALYSIS") {
  $("#analysis-modal-title").textContent = title;
  $("#analysis-modal-eyebrow").textContent = eyebrow;
  $("#analysis-modal").classList.toggle("figure-modal", eyebrow === "FIGURE READING");
  $("#analysis-modal-body").innerHTML = `<div class="analysis-loading">正在生成，请稍候…</div>`;
  $("#analysis-modal").classList.remove("hidden");
}

function closeAnalysis() {
  $("#analysis-modal").classList.add("hidden");
  $("#analysis-modal").classList.remove("figure-modal");
}

async function saveSettings() {
  const button = $("#save-settings");
  const message = $("#settings-message");
  button.disabled = true;
  message.textContent = "正在保存…";
  try {
    state.model = await postJson("/api/model", {
      baseUrl: $("#setting-base-url").value,
      model: $("#setting-model").value,
      apiKey: $("#setting-api-key").value,
    });
    message.textContent = "配置已保存。";
    if (state.selected) renderDetail(state.selected);
    setTimeout(closeSettings, 500);
  } catch (error) {
    message.textContent = error.message || String(error);
  } finally {
    button.disabled = false;
  }
}

async function analyzeSummary(item, force = false) {
  const cached = item.analysis?.summary;
  const button = $("#analyze-summary");
  const panel = $("#analysis-modal-body");
  button.disabled = true;
  button.textContent = "正在解读…";
  openAnalysis("论文解读");
  try {
    const result = cached && !force ? { ...item.analysis, summary: cached, model: item.analysis.model, cached: true } : await postJson(`/api/items/${item.key}/summary`, { force });
    item.analysis = { ...(item.analysis || {}), ...result };
    loadItems({ quiet: true });
    const labels = {
      research_question: ["研究问题", "⌁"],
      methods: ["方法与数据", "◌"],
      findings: ["主要发现", "✦"],
      limitations: ["局限性", "△"],
    };
    panel.innerHTML = Object.entries(labels).map(([key, [label, icon]]) => `
      <div class="summary-card"><div class="summary-label"><span>${icon}</span>${label}</div><p>${escapeHtml(result.summary[key] || "原文未说明")}</p></div>
    `).join("") + `<div class="summary-source">${result.cached ? "已读取本地保存结果" : "已保存到本地"} · 模型：${escapeHtml(result.model || "未说明")} · 请结合原文页码核对</div><button id="regenerate-analysis" class="secondary-button regenerate-button">重新生成（消耗 Token）</button>`;
    $("#regenerate-analysis").addEventListener("click", () => analyzeSummary(item, true));
    panel.scrollTop = 0;
  } catch (error) {
    panel.innerHTML = `<div class="analysis-error">${escapeHtml(error.message || String(error))}</div>`;
  } finally {
    button.disabled = false;
    button.textContent = item.analysis?.summary ? "查看论文解读" : "生成论文解读";
  }
}

async function extractTerms(item, force = false) {
  const cached = item.analysis?.terms;
  const button = $("#extract-terms");
  const panel = $("#analysis-modal-body");
  button.disabled = true;
  button.textContent = "提取中…";
  openAnalysis("专业术语", "TERM EXTRACTION");
  try {
    const result = cached && !force ? { ...item.analysis, terms: cached, model: item.analysis.model, cached: true } : await postJson(`/api/items/${item.key}/terms`, { force });
    item.analysis = { ...(item.analysis || {}), ...result };
    loadItems({ quiet: true });
    if (!result.terms?.length) {
      panel.innerHTML = `<div class="terms-empty">模型没有识别出足够明确的专业术语。</div>`;
    } else {
      panel.innerHTML = `<div class="terms-heading"><span>专业术语</span><small>共 ${result.terms.length} 个 · 请结合原文核对</small></div>` + result.terms.map((term) => `
        <div class="term-card"><div class="term-top"><strong>${escapeHtml(term.term)}</strong>${term.page ? `<span>第 ${escapeHtml(term.page)} 页</span>` : ""}</div><p class="term-explanation">${escapeHtml(term.explanation)}</p><p class="term-context"><span>本文语境</span>${escapeHtml(term.context)}</p></div>
      `).join("") + `<div class="summary-source">${result.cached ? "已读取本地保存结果" : "已保存到本地"} · 模型：${escapeHtml(result.model || "未说明")}</div><button id="regenerate-terms" class="secondary-button regenerate-button">重新提取（消耗 Token）</button>`;
    }
    if (result.terms?.length) $("#regenerate-terms").addEventListener("click", () => extractTerms(item, true));
    panel.scrollTop = 0;
  } catch (error) {
    panel.innerHTML = `<div class="analysis-error">${escapeHtml(error.message || String(error))}</div>`;
  } finally {
    button.disabled = false;
    button.textContent = item.analysis?.terms ? "查看专业术语" : "提取专业术语";
  }
}

function figureKey(attachmentKey, page, region = null) {
  return `${attachmentKey}:${page}${region ? `:crop:${region.join(",")}` : ""}`;
}

function figureCache(item, attachmentKey, page, region = null) {
  return item.analysis?.figures?.[figureKey(attachmentKey, page, region)] || null;
}

function renderFigureResult(item, pdf, page, region = null) {
  const target = $("#figure-result");
  if (!target) return;
  const cached = figureCache(item, pdf.key, page, region);
  if (!cached) {
    target.innerHTML = `<div class="figure-empty">${region ? "已选中图表区域。可拖动重新框选，建议包含图题、坐标轴和图例。" : "可点击“框选图表”，在左侧拖出一个选区。也可直接解析整页。"} 点击解析才会调用模型并消耗 Token。</div>`;
    return;
  }
  const cards = [
    ["图表内容", "description", "▦"],
    ["主要趋势", "trends", "↗"],
    ["核心结论", "takeaway", "✦"],
    ["注意事项", "caveats", "△"],
  ];
  target.innerHTML = cards.map(([label, key, icon]) => `<div class="figure-card"><div class="summary-label"><span>${icon}</span>${label}</div><p>${escapeHtml(cached[key] || "图中无法确认")}</p></div>`).join("") +
    `<div class="summary-source">已保存到本地 · 第 ${escapeHtml(cached.page || page)} 页 · ${region ? "框选区域" : "整页"} · 模型：${escapeHtml(cached.model || item.analysis?.model || "未说明")}</div>`;
}

function wireFigureWorkspace(item, pdf, pageCount, initialPage) {
  const panel = $("#analysis-modal-body");
  const pageInput = $("#figure-page");
  const pageStatus = $("#figure-page-status");
  const preview = $("#figure-preview");
  const runButton = $("#run-figure");
  const prevButton = $("#figure-prev-page");
  const nextButton = $("#figure-next-page");
  const zoomLabel = $("#figure-zoom-label");
  const viewport = $(".figure-preview-viewport");
  const stage = $("#figure-stage");
  const selection = $("#figure-selection");
  const cropButton = $("#figure-crop");
  const savedSelect = $("#figure-saved");
  const workspace = { item, pdf, page: initialPage, region: null, busy: false, request: null };
  panel.figureWorkspace = workspace;
  let zoom = 1;
  let currentPage = initialPage;
  let selecting = false;
  let start = null;
  const drawRegion = () => {
    const region = workspace.region;
    selection.hidden = !region;
    if (region) {
      const [x, y, width, height] = region;
      Object.assign(selection.style, { left: `${x / 10}%`, top: `${y / 10}%`, width: `${width / 10}%`, height: `${height / 10}%` });
    }
  };
  const refresh = () => {
    drawRegion();
    const cached = figureCache(item, pdf.key, currentPage, workspace.region);
    const busy = workspace.busy;
    runButton.disabled = busy || !preview.complete || !preview.naturalWidth;
    runButton.textContent = busy ? "正在解析…" : cached ? "重新解析（消耗 Token）" : workspace.region ? "解析所选图表（消耗 Token）" : "解析整页（消耗 Token）";
    cropButton.disabled = busy || !preview.complete || !preview.naturalWidth;
    panel.querySelectorAll("#figure-page, #figure-prev-page, #figure-next-page, #figure-clear-crop, #figure-saved").forEach(el => { el.disabled = busy; });
    prevButton.disabled = busy || currentPage <= 1;
    nextButton.disabled = busy || currentPage >= pageCount;
    renderFigureResult(item, pdf, currentPage, workspace.region);
    const entries = Object.entries(item.analysis?.figures || {}).filter(([key, value]) => key.startsWith(`${pdf.key}:`) && value.page === currentPage);
    savedSelect.innerHTML = `<option value="">本页已保存的解析（${entries.length}）</option>` + entries.map(([key, value], index) => `<option value="${escapeHtml(key)}">${value.region ? `图表选区 ${index + 1}` : "整页解析"}</option>`).join("");
    const activeKey = figureKey(pdf.key, currentPage, workspace.region);
    if (cached) savedSelect.value = activeKey;
  };
  workspace.refresh = refresh;
  const updateZoom = () => {
    stage.style.width = `${Math.round(zoom * 100)}%`;
    zoomLabel.textContent = `${Math.round(zoom * 100)}%`;
  };
  const updatePage = (requestedPage = Number.parseInt(pageInput.value, 10) || currentPage || 1) => {
    const page = Math.max(1, Math.min(pageCount, requestedPage));
    currentPage = page;
    workspace.page = page;
    const savedPage = Object.values(item.analysis?.figures || {}).find(value => value.attachmentKey === pdf.key && value.page === page);
    workspace.region = figureCache(item, pdf.key, page) ? null : savedPage?.region || null;
    pageInput.value = page;
    pageStatus.textContent = `第 ${page} 页 / 共 ${pageCount} 页`;
    preview.src = `/api/attachments/${encodeURIComponent(pdf.key)}/page-image?page=${page}`;
    viewport.scrollTo(0, 0);
    refresh();
  };
  preview.onload = refresh;
  preview.onerror = () => { refresh(); $("#figure-result").textContent = "页面预览加载失败，请切换页面后重试。"; };
  cropButton.onclick = () => {
    selecting = !selecting;
    cropButton.textContent = selecting ? "结束框选" : "框选图表";
    cropButton.setAttribute("aria-pressed", String(selecting));
    stage.classList.toggle("selecting", selecting);
  };
  $("#figure-clear-crop").onclick = () => { workspace.region = null; refresh(); };
  savedSelect.onchange = () => {
    const saved = item.analysis?.figures?.[savedSelect.value];
    if (saved) { workspace.region = saved.region || null; refresh(); }
  };
  const point = (event) => {
    const rect = preview.getBoundingClientRect();
    return [Math.max(0, Math.min(1000, Math.round((event.clientX - rect.left) * 1000 / rect.width))), Math.max(0, Math.min(1000, Math.round((event.clientY - rect.top) * 1000 / rect.height)))];
  };
  stage.onpointerdown = (event) => {
    if (!selecting || workspace.busy || event.button !== 0 || !preview.complete || !preview.naturalWidth) return;
    event.preventDefault();
    start = point(event);
    stage.setPointerCapture(event.pointerId);
  };
  stage.onpointermove = (event) => {
    if (!start) return;
    const end = point(event);
    workspace.region = [Math.min(start[0], end[0]), Math.min(start[1], end[1]), Math.abs(end[0] - start[0]), Math.abs(end[1] - start[1])];
    drawRegion();
  };
  stage.onpointerup = (event) => {
    if (!start) return;
    start = null;
    if (stage.hasPointerCapture(event.pointerId)) stage.releasePointerCapture(event.pointerId);
    if (!workspace.region || workspace.region[2] < 10 || workspace.region[3] < 10) workspace.region = null;
    refresh();
  };
  stage.onpointercancel = () => { start = null; workspace.region = null; refresh(); };
  runButton.onclick = () => runFigureAnalysis(workspace);
  prevButton.addEventListener("click", () => updatePage(currentPage - 1));
  nextButton.addEventListener("click", () => updatePage(currentPage + 1));
  pageInput.addEventListener("change", () => updatePage());
  pageInput.addEventListener("keydown", (event) => { if (event.key === "Enter") updatePage(); });
  $("#figure-zoom-out").addEventListener("click", () => { zoom = Math.max(.75, +(zoom - .15).toFixed(2)); updateZoom(); });
  $("#figure-zoom-in").addEventListener("click", () => { zoom = Math.min(2.5, +(zoom + .15).toFixed(2)); updateZoom(); });
  $("#figure-zoom-reset").addEventListener("click", () => { zoom = 1; updateZoom(); });
  $("#figure-open-image").addEventListener("click", () => window.open(preview.src, "_blank"));
  updateZoom();
  updatePage(initialPage);
}

async function runFigureAnalysis(workspace) {
  if (workspace.busy) return;
  const { item, pdf, page, region } = workspace;
  const force = Boolean(figureCache(item, pdf.key, page, region));
  const panel = $("#analysis-modal-body");
  workspace.busy = true;
  workspace.refresh();
  const button = $("#run-figure");
  try {
    const result = await postJson(`/api/items/${item.key}/figure`, { attachmentKey: pdf.key, page, region, force });
    item.analysis = { ...(item.analysis || {}), ...result };
    loadItems({ quiet: true });
    workspace.busy = false;
    if (panel.figureWorkspace === workspace && $("#run-figure") === button) workspace.refresh();
  } catch (error) {
    workspace.busy = false;
    if (panel.figureWorkspace === workspace && $("#run-figure") === button) {
      workspace.refresh();
      $("#figure-result").insertAdjacentHTML("afterbegin", `<div class="analysis-error">${escapeHtml(error.message || String(error))}</div>`);
    }
  }
}

async function analyzeFigure(item, pdf) {
  openAnalysis("图表解析", "FIGURE READING");
  const panel = $("#analysis-modal-body");
  try {
    const cachedPages = Object.keys(item.analysis?.figures || {})
      .filter((key) => key.startsWith(`${pdf.key}:`))
      .map((key) => Number.parseInt(key.split(":")[1], 10))
      .filter(Number.isFinite);
    const preferredPage = cachedPages[0] || 1;
    const firstPage = await getJson(`/api/attachments/${encodeURIComponent(pdf.key)}/text?page=1`);
    const pageCount = firstPage.pageCount || 1;
    const page = Math.max(1, Math.min(pageCount, preferredPage));
    panel.innerHTML = `
      <div class="figure-intro">用预览两侧的箭头连续翻页，找到图表后再点击解析。可用“＋”放大细节，或打开原图查看高清页面。</div>
      <div class="figure-workspace">
        <section class="figure-pane figure-pdf-pane">
          <div class="figure-pane-title"><span>PDF 页面</span><span id="figure-page-status"></span></div>
          <div class="figure-controls"><label>页码 <input id="figure-page" type="number" min="1" max="${pageCount}" value="${page}" /></label><div class="figure-zoom-controls"><button id="figure-zoom-out" class="zoom-button" title="缩小">−</button><span id="figure-zoom-label">100%</span><button id="figure-zoom-in" class="zoom-button" title="放大">+</button><button id="figure-zoom-reset" class="secondary-button">适应宽度</button><button id="figure-open-image" class="secondary-button">打开原图</button></div></div>
          <div class="crop-controls"><button id="figure-crop" class="secondary-button" aria-pressed="false">框选图表</button><button id="figure-clear-crop" class="secondary-button">取消选区</button><span>请把图题、坐标轴和图例一起框入</span></div>
          <div class="figure-preview-wrap"><button id="figure-prev-page" class="figure-side-button left" aria-label="上一页">‹</button><div class="figure-preview-viewport"><div id="figure-stage"><img id="figure-preview" class="figure-preview" draggable="false" alt="PDF 页面预览" /><div id="figure-selection" hidden></div></div></div><button id="figure-next-page" class="figure-side-button right" aria-label="下一页">›</button></div>
        </section>
        <section class="figure-pane figure-analysis-pane">
          <div class="figure-pane-title"><span>图表解析</span><small>结果会保存到当前文献</small></div>
          <div class="figure-run"><button id="run-figure" class="primary-button">解析本页图表</button></div>
          <select id="figure-saved" aria-label="查看本页保存的图表解析"></select>
          <div id="figure-result"></div>
        </section>
      </div>`;
    wireFigureWorkspace(item, pdf, pageCount, page);
  } catch (error) {
    panel.innerHTML = `<div class="analysis-error">${escapeHtml(error.message || String(error))}</div>`;
  }
}

function selectItem(key) {
  state.listScroll = window.scrollY;
  history.pushState({ paperFromLibrary: true }, "", `#/items/${encodeURIComponent(key)}`);
  applyRoute();
}

async function applyRoute() {
  const request = ++state.detailRequest;
  const match = location.hash.match(/^#\/items\/([A-Z0-9]+)$/);
  const detail = $("#detail");
  $("#library").classList.toggle("hidden", Boolean(match));
  detail.classList.toggle("hidden", !match);
  closeAnalysis();
  if (!match) {
    const selectedKey = state.selected?.key;
    state.selected = null;
    document.title = "文献梳理工具";
    renderItems();
    window.scrollTo(0, state.listScroll);
    document.querySelector(`.item-card[data-key="${selectedKey}"]`)?.focus({ preventScroll: true });
    return;
  }
  state.selected = null;
  document.title = "正在打开文献 · 文献梳理工具";
  window.scrollTo(0, 0);
  detail.innerHTML = `<button id="close-detail" class="back-button">← 返回文献列表</button><p role="status" class="analysis-loading">正在打开文献…</p>`;
  $("#close-detail").addEventListener("click", closeDetail);
  try {
    const [item, analysis] = await Promise.all([
      getJson(`/api/items/${match[1]}`), getJson(`/api/items/${match[1]}/analysis`),
    ]);
    if (request !== state.detailRequest) return;
    state.selected = { ...item, analysis };
    document.title = `${item.title} · 文献梳理工具`;
    renderDetail(state.selected);
    detail.querySelector("h2").focus({ preventScroll: true });
  } catch (error) {
    if (request !== state.detailRequest) return;
    detail.insertAdjacentHTML("beforeend", `<p class="message" role="alert">${escapeHtml(error.message || String(error))}</p>`);
    detail.querySelector(".analysis-loading")?.remove();
  }
}

async function loadItems({ quiet = false } = {}) {
  const request = ++state.libraryRequest;
  state.libraryLoading = true;
  $("#refresh-library").disabled = true;
  if (!quiet) $("#sync-status").textContent = "正在读取本机 Zotero 和已保存分析…";
  try {
    const params = new URLSearchParams({ limit: "100", status: state.progressFilter });
    if (state.collection) params.set("collection", state.collection);
    if (state.query) params.set("q", state.query);
    const result = await getJson(`/api/library?${params}`);
    if (request !== state.libraryRequest) return;
    const deletedCollection = Boolean(state.collection && !result.collection);
    state.collection = result.collection;
    state.allCount = result.itemCount;
    state.items = result.items;
    $("#health").textContent = `Zotero ${result.zoteroVersion || "已连接"} · ${result.itemCount} 篇`;
    $("#health").className = "health ok";
    $("#message").classList.add("hidden");
    renderCollections(result.collections);
    renderProgress(result.progress, result.matchingCount);
    renderItems();
    state.lastSync = Date.now();
    $("#sync-status").textContent = `${deletedCollection ? "当前集合已在 Zotero 删除，已切换全部文献。" : ""}本机更新于 ${new Date(state.lastSync).toLocaleTimeString("zh-CN", { hour12: false })} · 自动更新`;
  } catch (error) {
    if (request !== state.libraryRequest) return;
    if (!state.lastSync) {
      $("#health").textContent = "文献库连接失败";
      $("#health").className = "health error";
    }
    $("#sync-status").textContent = "刷新失败，请重试；上次读取的内容暂时保留。";
    showError(error);
  } finally {
    if (request === state.libraryRequest) {
      state.libraryLoading = false;
      $("#refresh-library").disabled = false;
    }
  }
}

async function boot() {
  try {
    await Promise.all([getJson("/api/model").then((model) => { state.model = model; }), loadItems()]);
    if (!location.hash) history.replaceState(null, "", "#/library");
    history.scrollRestoration = "manual";
    window.addEventListener("popstate", applyRoute);
    await applyRoute();
  } catch (error) {
    $("#health").textContent = "连接失败";
    $("#health").className = "health error";
    showError(error);
  }
}

let searchTimer;
$("#search").addEventListener("input", (event) => {
  clearTimeout(searchTimer);
  state.libraryRequest++;
  state.query = event.target.value.trim();
  searchTimer = setTimeout(() => loadItems(), 250);
});
document.querySelectorAll(".progress-card").forEach((button) => button.addEventListener("click", () => {
  state.progressFilter = state.progressFilter === button.dataset.status ? "all" : button.dataset.status;
  loadItems();
}));
$("#clear-progress-filter").addEventListener("click", () => { state.progressFilter = "all"; loadItems(); });
$("#refresh-library").addEventListener("click", () => loadItems());
function refreshIfVisible() {
  if (!document.hidden && !state.libraryLoading && Date.now() - state.lastSync > 5000) loadItems({ quiet: true });
}
window.addEventListener("focus", refreshIfVisible);
document.addEventListener("visibilitychange", refreshIfVisible);
setInterval(refreshIfVisible, 30000);
$("#settings-button").addEventListener("click", openSettings);
$("#close-settings").addEventListener("click", closeSettings);
$("#cancel-settings").addEventListener("click", closeSettings);
$("#save-settings").addEventListener("click", saveSettings);
$("#settings-modal").addEventListener("click", (event) => { if (event.target.id === "settings-modal") closeSettings(); });
$("#close-analysis").addEventListener("click", closeAnalysis);
$("#analysis-modal").addEventListener("click", (event) => { if (event.target.id === "analysis-modal") closeAnalysis(); });
boot();
