const state = { collection: "", query: "", items: [], selected: null, model: null };
const $ = (s) => document.querySelector(s);

function escapeHtml(value = "") {
  return String(value).replace(/[&<>'"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
}

function initials(item) {
  const text = item.creators?.[0] || item.title || "文";
  return text.trim().slice(0, 1).toUpperCase();
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
  document.querySelectorAll(".collection").forEach((button) => button.addEventListener("click", () => {
    state.collection = button.dataset.key;
    state.query = "";
    $("#search").value = "";
    $("#section-title").textContent = button.querySelector("span").textContent;
    document.querySelectorAll(".collection").forEach((b) => b.classList.toggle("active", b === button));
    loadItems();
  }));
}

function renderItems() {
  const target = $("#items");
  if (!state.items.length) {
    target.innerHTML = `<div class="no-results"><div>⌁</div><p>没有找到匹配的文献</p><small>可以换一个关键词，或切换左侧集合</small></div>`;
    return;
  }
  target.innerHTML = state.items.map((item) => `
    <button class="item-card ${state.selected?.key === item.key ? "selected" : ""}" data-key="${item.key}">
      <div class="item-mark">${escapeHtml(initials(item))}</div>
      <div class="item-main">
        <div class="item-type">${escapeHtml(item.itemType)} ${item.attachments?.length ? "· PDF" : ""}</div>
        <h3>${escapeHtml(item.title)}</h3>
        <p>${escapeHtml(item.creators?.join(" · ") || "作者信息未填写")}</p>
        <div class="item-meta">${escapeHtml(item.publicationTitle || "")}${item.date ? ` · ${escapeHtml(item.date)}` : ""}</div>
      </div>
      <div class="arrow">›</div>
    </button>
  `).join("");
  document.querySelectorAll(".item-card").forEach((card) => card.addEventListener("click", () => selectItem(card.dataset.key)));
}

function renderDetail(item) {
  const detail = $("#detail");
  detail.classList.remove("empty");
  const pdf = item.attachments?.find((a) => a.contentType === "application/pdf" && a.exists);
  const hasFigureCache = Boolean(pdf && Object.keys(item.analysis?.figures || {}).some((key) => key.startsWith(`${pdf.key}:`)));
  detail.innerHTML = `
    <div class="detail-top"><span class="pill">${escapeHtml(item.itemType)}</span><span class="key">${escapeHtml(item.key)}</span></div>
    <h2>${escapeHtml(item.title)}</h2>
    <div class="detail-authors">${escapeHtml(item.creators?.join(" · ") || "作者信息未填写")}</div>
    <dl class="facts">
      ${item.publicationTitle ? `<div><dt>期刊 / 来源</dt><dd>${escapeHtml(item.publicationTitle)}</dd></div>` : ""}
      ${item.date ? `<div><dt>日期</dt><dd>${escapeHtml(item.date)}</dd></div>` : ""}
      ${item.doi ? `<div><dt>DOI</dt><dd>${escapeHtml(item.doi)}</dd></div>` : ""}
      ${item.pages ? `<div><dt>页码</dt><dd>${escapeHtml(item.pages)}</dd></div>` : ""}
    </dl>
    <div class="detail-section"><div class="section-label">摘要</div><p class="abstract">${escapeHtml(item.abstract || "这篇文献没有记录摘要。")}</p></div>
    <div class="detail-section"><div class="section-label">附件</div>
      ${item.attachments?.length ? item.attachments.map(a => `<div class="attachment"><span class="pdf-icon">PDF</span><span class="attachment-name">${escapeHtml(a.filename || "附件")}</span><em>${a.exists ? "已找到" : "未找到"}</em></div>`).join("") : `<p class="muted">暂无 PDF 附件</p>`}
      ${pdf ? `<div class="reader-actions"><button id="read-pdf" class="primary-button">打开 PDF ↗</button></div>` : ""}
    </div>
    <div class="analysis-actions"><button id="analyze-summary" class="primary-button">${item.analysis?.summary ? "查看论文解读" : "生成论文解读"}</button><button id="extract-terms" class="secondary-button">${item.analysis?.terms ? "查看专业术语" : "提取专业术语"}</button>${pdf ? `<button id="analyze-figure" class="secondary-button">${hasFigureCache ? "查看图表解析" : "图表解析"}</button>` : ""}<span>${state.model?.configured ? `已配置：${escapeHtml(state.model.model)}` : "需配置模型"}</span></div>
    <div class="next-feature"><span>✦</span><div><strong>逐页理解</strong><br><small>选择 PDF 页码后，可预览并解析本页图表；结果会保存在当前文献下。</small></div></div>
  `;
  $("#analyze-summary").addEventListener("click", () => analyzeSummary(item));
  $("#extract-terms").addEventListener("click", () => extractTerms(item));
  if (pdf) $("#analyze-figure").addEventListener("click", () => analyzeFigure(item, pdf));
  if (pdf) {
    $("#read-pdf").addEventListener("click", () => window.open(`/api/attachments/${pdf.key}/file`, "_blank"));
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

function figureCache(item, attachmentKey, page) {
  return item.analysis?.figures?.[`${attachmentKey}:${page}`] || null;
}

function renderFigureResult(item, pdf, page) {
  const target = $("#figure-result");
  if (!target) return;
  const cached = figureCache(item, pdf.key, page);
  if (!cached) {
    target.innerHTML = `<div class="figure-empty">页面预览已加载。确认页码后，点击“解析本页图表”开始消耗 Token。</div>`;
    return;
  }
  const cards = [
    ["图表内容", "description", "▦"],
    ["主要趋势", "trends", "↗"],
    ["核心结论", "takeaway", "✦"],
    ["注意事项", "caveats", "△"],
  ];
  target.innerHTML = cards.map(([label, key, icon]) => `<div class="figure-card"><div class="summary-label"><span>${icon}</span>${label}</div><p>${escapeHtml(cached[key] || "图中无法确认")}</p></div>`).join("") +
    `<div class="summary-source">已读取本地保存结果 · 第 ${escapeHtml(cached.page || page)} 页 · 模型：${escapeHtml(item.analysis?.model || "未说明")}</div>` +
    `<button id="regenerate-figure" class="secondary-button regenerate-button">重新解析（消耗 Token）</button>`;
  $("#regenerate-figure").addEventListener("click", () => runFigureAnalysis(item, pdf, page, true));
}

function wireFigureWorkspace(item, pdf, pageCount, initialPage) {
  const pageInput = $("#figure-page");
  const pageStatus = $("#figure-page-status");
  const preview = $("#figure-preview");
  const runButton = $("#run-figure");
  const prevButton = $("#figure-prev-page");
  const nextButton = $("#figure-next-page");
  const zoomLabel = $("#figure-zoom-label");
  let zoom = 1;
  let currentPage = initialPage;
  const updateZoom = () => {
    preview.style.width = `${Math.round(zoom * 100)}%`;
    zoomLabel.textContent = `${Math.round(zoom * 100)}%`;
  };
  const updatePage = (requestedPage = Number.parseInt(pageInput.value, 10) || currentPage || 1) => {
    const page = Math.max(1, Math.min(pageCount, requestedPage));
    currentPage = page;
    pageInput.value = page;
    pageStatus.textContent = `第 ${page} 页 / 共 ${pageCount} 页`;
    preview.src = `/api/attachments/${encodeURIComponent(pdf.key)}/page-image?page=${page}`;
    prevButton.disabled = page <= 1;
    nextButton.disabled = page >= pageCount;
    renderFigureResult(item, pdf, page);
    const cached = figureCache(item, pdf.key, page);
    runButton.textContent = cached ? "重新解析（消耗 Token）" : "解析本页图表";
    runButton.classList.toggle("secondary-button", Boolean(cached));
    runButton.classList.toggle("primary-button", !cached);
    runButton.onclick = () => runFigureAnalysis(item, pdf, page, Boolean(cached));
  };
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

async function runFigureAnalysis(item, pdf, page, force = false) {
  const button = $("#run-figure");
  if (button) { button.disabled = true; button.textContent = "正在解析…"; }
  try {
    const result = await postJson(`/api/items/${item.key}/figure`, { attachmentKey: pdf.key, page, force });
    item.analysis = { ...(item.analysis || {}), ...result };
    renderFigureResult(item, pdf, result.figure?.page || page);
    const pageInput = $("#figure-page");
    if (pageInput) pageInput.value = result.figure?.page || page;
    const run = $("#run-figure");
    if (run) {
      run.disabled = false;
      run.textContent = "重新解析（消耗 Token）";
      run.classList.add("secondary-button");
      run.classList.remove("primary-button");
      run.onclick = () => runFigureAnalysis(item, pdf, result.figure?.page || page, true);
    }
  } catch (error) {
    $("#figure-result").innerHTML = `<div class="analysis-error">${escapeHtml(error.message || String(error))}</div>`;
    if (button) button.disabled = false;
  }
}

async function analyzeFigure(item, pdf) {
  openAnalysis("图表解析", "FIGURE READING");
  const panel = $("#analysis-modal-body");
  try {
    const cachedPages = Object.keys(item.analysis?.figures || {})
      .filter((key) => key.startsWith(`${pdf.key}:`))
      .map((key) => Number.parseInt(key.split(":").pop(), 10))
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
          <div class="figure-preview-wrap"><button id="figure-prev-page" class="figure-side-button left" aria-label="上一页">‹</button><div class="figure-preview-viewport"><img id="figure-preview" class="figure-preview" alt="PDF 页面预览" /></div><button id="figure-next-page" class="figure-side-button right" aria-label="下一页">›</button></div>
        </section>
        <section class="figure-pane figure-analysis-pane">
          <div class="figure-pane-title"><span>图表解析</span><small>结果会保存到当前文献</small></div>
          <div class="figure-run"><button id="run-figure" class="primary-button">解析本页图表</button></div>
          <div id="figure-result"></div>
        </section>
      </div>`;
    wireFigureWorkspace(item, pdf, pageCount, page);
  } catch (error) {
    panel.innerHTML = `<div class="analysis-error">${escapeHtml(error.message || String(error))}</div>`;
  }
}

async function selectItem(key) {
  try {
    state.selected = await getJson(`/api/items/${key}`);
    state.selected.analysis = await getJson(`/api/items/${key}/analysis`);
    renderItems();
    renderDetail(state.selected);
  } catch (error) { showError(error); }
}

async function loadItems() {
  try {
    $("#message").classList.add("hidden");
    const params = new URLSearchParams({ limit: "100" });
    if (state.collection) params.set("collection", state.collection);
    if (state.query) params.set("q", state.query);
    state.items = await getJson(`/api/items?${params}`);
    renderItems();
  } catch (error) { showError(error); }
}

async function boot() {
  try {
    const health = await getJson("/api/health");
    state.model = await getJson("/api/model");
    state.allCount = health.itemCount;
    $("#health").textContent = `Zotero ${health.zoteroVersion || "已连接"} · ${health.itemCount} 篇`;
    $("#health").className = "health ok";
    const collections = await getJson("/api/collections");
    renderCollections(collections);
    await loadItems();
  } catch (error) {
    $("#health").textContent = "连接失败";
    $("#health").className = "health error";
    showError(error);
  }
}

let searchTimer;
$("#search").addEventListener("input", (event) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { state.query = event.target.value.trim(); loadItems(); }, 250);
});
$("#settings-button").addEventListener("click", openSettings);
$("#close-settings").addEventListener("click", closeSettings);
$("#cancel-settings").addEventListener("click", closeSettings);
$("#save-settings").addEventListener("click", saveSettings);
$("#settings-modal").addEventListener("click", (event) => { if (event.target.id === "settings-modal") closeSettings(); });
$("#close-analysis").addEventListener("click", closeAnalysis);
$("#analysis-modal").addEventListener("click", (event) => { if (event.target.id === "analysis-modal") closeAnalysis(); });
boot();
