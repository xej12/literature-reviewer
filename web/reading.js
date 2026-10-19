const readingTiers = ["夯", "顶级", "人上人", "NPC", "拉"];
const metricStatusLabels = { unmatched: "期刊指标待核实", ambiguous: "刊名匹配有歧义，待核实", issn_unmatched: "ISSN 未匹配，待核实", not_applicable: "非期刊或预印本：期刊指标不适用", data_unavailable: "期刊数据尚未载入" };

function tierClass(tier) { return `tier-${readingTiers.indexOf(tier) < 0 ? "pending" : readingTiers.indexOf(tier)}`; }

function metricBadges(item) {
  const metrics = item.journalMetrics;
  if (!metrics) return "";
  const cas = metrics.cas, jcr = metrics.jcr;
  const quartiles = [...new Set((jcr?.subjects || []).map(s => s.quartile).filter(q => /^Q[1-4]$/.test(q)))].sort();
  return `<div class="metric-badges" aria-label="期刊指标">
    ${cas ? `<span class="metric-badge cas">中科院 ${cas.division ? cas.division + " 区" : "待核实"} · ${cas.year}${cas.top ? " · Top" : ""}</span>` : ""}
    ${jcr ? `<span class="metric-badge">IF ${jcr.impactFactor ?? "未收录"} · ${jcr.year}</span><span class="metric-badge">JCR ${escapeHtml(quartiles.join(" / ") || "未收录分区")} · ${jcr.year}</span>` : ""}
    ${!cas && !jcr ? `<span class="metric-badge muted-metric">${escapeHtml(metricStatusLabels[metrics.status] || "指标待核实")}</span>` : !cas ? `<span class="metric-badge muted-metric">中科院待核实</span>` : !jcr ? `<span class="metric-badge muted-metric">JCR / IF 待核实</span>` : ""}
  </div>`;
}

function priorityBadge(item) {
  const p = item.readingPriority || { tier: "待评估" };
  return `<span class="tier-badge ${tierClass(p.tier)}">${escapeHtml(p.tier)}</span><span class="priority-method">${p.method === "manual" ? "手动设定" : p.method === "model" ? (p.tier === "待评估" ? "答复已保存 · 待核实" : "评估已保存") : p.stale ? "方向或材料已变，需重新评估" : "尚未评估内容"}</span>`;
}

function unverifiedQuotes(p) {
  const quotes = Array.isArray(p.unverifiedEvidence) ? p.unverifiedEvidence : [p.unverifiedEvidence];
  return quotes.map(q => typeof q === "string" ? q : q?.quote || q?.text).filter(q => typeof q === "string").slice(0, 5);
}

function journalDetails(item) {
  const metrics = item.journalMetrics;
  if (!metrics) return "";
  const cas = metrics.cas, jcr = metrics.jcr;
  return `<section class="journal-section"><h3>期刊指标</h3>${metricBadges(item)}
    ${cas || jcr ? `<details class="journal-details"><summary>查看学科分区与匹配依据</summary>
      ${item.issn ? `<p>文献 ISSN：${escapeHtml(item.issn)}</p>` : ""}
      ${cas ? `<h4>中科院 ${cas.year} · ${escapeHtml(cas.category)} · ${cas.division || "待核实"} 区</h4><p>期刊：${escapeHtml(cas.journal)} · ${cas.match === "issn" ? "按 ISSN 匹配" : "按规范刊名精确匹配"}</p><ul>${cas.subjects.map(s => `<li>${escapeHtml(s.category)}：${s.division || "待核实"} 区 <small>${escapeHtml(s.rank)}</small></li>`).join("")}</ul>` : ""}
      ${jcr ? `<h4>JCR ${jcr.year} · IF ${jcr.impactFactor ?? "未收录"}</h4><p>期刊：${escapeHtml(jcr.journal)} · ${jcr.match === "issn" ? "按 ISSN 匹配" : "按规范刊名精确匹配"}</p><ul>${jcr.subjects.map(s => `<li>${escapeHtml(s.category)}：${escapeHtml(s.quartile || "待核实")} <small>${escapeHtml(s.rank)}</small></li>`).join("")}</ul>` : ""}
    </details>` : ""}
    <p class="metrics-source">来源：<a href="${escapeHtml(metrics.sourceUrl)}" target="_blank" rel="noopener">${escapeHtml(metrics.source)}</a>。${escapeHtml(metrics.notice)}</p></section>`;
}

function paperPriority(item) {
  const p = item.readingPriority || { tier: "待评估", signals: [] };
  const research = item.research || state.research;
  return `<div class="priority-heading"><h3>阅读优先级</h3><button id="edit-paper-research" class="text-button">修改研究方向</button></div>
    <p class="priority-goal">研究目标：${escapeHtml(research?.goal || "尚未设置")}</p>
    <div class="priority-title">${priorityBadge(item)}${p.score != null ? `<strong>${p.score} / 100</strong>` : ""}</div>
    <p class="priority-reason">${escapeHtml(p.reason || "尚未评价论文内容。")}</p>
    ${p.verificationNotice ? `<p class="priority-notice" role="status">${escapeHtml(p.verificationNotice)}</p>` : ""}
    ${p.stale ? `<p class="priority-notice">研究方向或文献材料已更新，旧评估仍保存在本电脑。本页需要按当前材料重新判断。</p>` : ""}
    ${p.signals?.length ? `<p class="priority-signals">相关性线索：${p.signals.map(escapeHtml).join("、")}（关键词匹配，不能据此判断必读）</p>` : `<p class="priority-signals">尚未匹配到研究关键词；这不表示论文没有阅读价值。</p>`}
    ${p.method === "model" ? `${p.score != null ? `<div class="priority-breakdown">相关性 ${p.relevance ?? "—"} / 60 · 内容价值 ${p.contentValue ?? "—"} / 30 · 期刊参考 ${p.journalPoints == null ? "缺失，不扣分，按内容归一化" : p.journalPoints + " / 10"}</div>` : ""}
      <details class="priority-evidence"><summary>${p.evidence?.length ? "核对评估依据与阅读范围" : "查看已保存答复与阅读范围"}</summary><p>${escapeHtml(p.basis || "")}</p>${(p.evidence || []).map(q => `<blockquote>${escapeHtml(q)}</blockquote>`).join("")}
      ${p.evidenceVerification === "unverified" ? `<p>以下是模型给出的引文，尚未在原文核实，不作为评分依据：</p>${unverifiedQuotes(p).map(q => `<blockquote>${escapeHtml(q)}</blockquote>`).join("")}${p.proposedScores ? `<p>模型建议分（未采用）：相关性 ${escapeHtml(p.proposedScores.relevance)} / 60 · 内容价值 ${escapeHtml(p.proposedScores.contentValue)} / 30</p>` : ""}` : ""}
      <p>${escapeHtml(p.limitations || "")}</p><small>模型：${escapeHtml(p.model || "")} · ${escapeHtml(p.updatedAt || "")}</small></details>` : ""}
    <div class="priority-actions"><button id="evaluate-priority" class="primary-button" ${research?.goal?.trim() ? "" : "disabled"}>${p.cached ? "重新评估" : "评估阅读优先级"}（消耗 Token）</button>${p.cached ? `<button id="reset-priority" class="text-button">清除当前等级</button>` : ""}<span>${research?.goal?.trim() ? "结果保存在本篇文献下，下次直接查看" : "请先设置自己的研究目标；也可免费手动设置等级"}</span></div>
    <details class="manual-priority"><summary>手动调整（不消耗 Token）</summary><div class="manual-fields"><label>阅读等级<select id="manual-tier">${readingTiers.map(t => `<option${t === p.tier ? " selected" : ""}>${t}</option>`).join("")}</select></label><label>我的理由<input id="manual-reason" placeholder="例如：与当前实验直接相关，本周精读" value="${p.method === "manual" ? escapeHtml(p.reason) : ""}" /></label><button id="save-manual-priority" class="secondary-button">保存等级</button></div></details>
    <p class="priority-footnote">夯 → 顶级 → 人上人 → NPC → 拉。等级仅表示对当前研究目标的阅读优先级；“夯”为优先精读，“拉”为当前低优先级。未评估文献单列。</p><p id="priority-message" class="priority-message" role="status"></p>`;
}

function wirePaperPriority(item) {
  $("#edit-paper-research").onclick = openResearch;
  $("#evaluate-priority").onclick = () => updatePriority(item, { action: "evaluate", force: Boolean(item.readingPriority?.cached) });
  $("#reset-priority")?.addEventListener("click", () => updatePriority(item, { action: "reset" }));
  $("#save-manual-priority").onclick = () => updatePriority(item, { action: "manual", tier: $("#manual-tier").value, reason: $("#manual-reason").value });
}

async function refreshPaperPriority(item) {
  try {
    const updated = await getJson(`/api/items/${item.key}`);
    if (state.selected !== item) return;
    item.readingPriority = updated.readingPriority;
    item.research = updated.research;
    $("#paper-priority").innerHTML = paperPriority(item);
    wirePaperPriority(item);
  } catch (error) {
    if (state.selected === item) $("#priority-message").textContent = `优先级刷新失败：${error.message}`;
  }
}

async function updatePriority(item, options) {
  const panel = $("#paper-priority");
  panel.querySelectorAll("button").forEach(b => b.disabled = true);
  $("#priority-message").textContent = options.action === "evaluate" ? "正在结合研究目标评估论文内容，请稍候…" : "正在保存…";
  try {
    const result = await postJson(`/api/items/${item.key}/priority`, { ...options, profileVersion: (item.research || state.research)?.version });
    item.readingPriority = result;
    if (state.selected?.key === item.key && panel.isConnected) {
      panel.innerHTML = paperPriority(item);
      wirePaperPriority(item);
      $("#priority-message").textContent = options.action === "reset" ? "已清除当前等级。" : result.cached ? "已保存，重复查看不消耗 Token。" : "已更新。";
    }
    loadItems({ quiet: true });
  } catch (error) {
    if (panel.isConnected) {
      $("#priority-message").textContent = error.message;
      panel.querySelectorAll("button").forEach(b => b.disabled = false);
      $("#evaluate-priority").disabled = !(item.research || state.research)?.goal?.trim();
    }
  }
}

let researchOpenRequest = 0;
async function openResearch() {
  if (!$("#research-modal").classList.contains("hidden")) { $("#research-goal").focus(); return; }
  const request = ++researchOpenRequest;
  try {
    const research = await getJson("/api/research");
    if (request !== researchOpenRequest) return;
    $("#research-goal").value = research.goal;
    $("#research-topics").value = research.topics;
    $("#research-message").textContent = "更改研究方向后，旧评估会保留，但不会套用到新的研究目标。";
    $("#research-modal").classList.remove("hidden");
    resetResearchSuggestion();
    $("#research-suggestion-tools").open = !research.goal.trim();
    $("#research-goal").focus();
  } catch (error) { showError(error); }
}

function closeResearch() { researchOpenRequest++; $("#research-modal").classList.add("hidden"); stopResearchSuggestion(); }

function renderReadingContext(result) {
  state.research = result.research;
  $("#research-summary").textContent = result.research?.goal || "尚未设置阅读目标 · 请设置自己的研究方向";
  const data = result.journalData;
  $("#journal-data-status").textContent = data?.ready ? `中科院 ${data.casYear} · JCR ${data.jcrYear} · ${data.source} · 期刊指标仅供参考` : "期刊数据未载入，仍可评估论文内容和手动设置阅读等级。";
  for (const kind of ["all", "available", "unavailable"]) $("#division-" + kind).textContent = result.divisionCounts?.[kind] ?? "—";
  document.querySelectorAll("[data-division]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.division === state.divisionFilter)));
}

function initReadingControls() {
  initResearchSuggestion();
  $("#edit-research").onclick = openResearch;
  $("#close-research").onclick = closeResearch;
  $("#cancel-research").onclick = closeResearch;
  $("#research-modal").onclick = e => { if (e.target.id === "research-modal") closeResearch(); };
  $("#reading-sort").onchange = e => { state.readingSort = e.target.value; loadItems(); };
  $("#reading-tier").onchange = e => { state.readingTier = e.target.value; loadItems(); };
  document.querySelectorAll("[data-division]").forEach(button => button.onclick = () => {
    clearTimeout(searchTimer);
    state.divisionFilter = button.dataset.division;
    loadItems();
  });
  $("#save-research").onclick = async () => {
    $("#save-research").disabled = true;
    try {
      state.research = await postJson("/api/research", { goal: $("#research-goal").value, topics: $("#research-topics").value });
      await loadItems({ quiet: true });
      if (state.selected) {
        const key = state.selected.key;
        const updated = await getJson(`/api/items/${key}`);
        if (state.selected?.key === key) {
          Object.assign(state.selected, updated);
          $("#paper-priority").innerHTML = paperPriority(state.selected);
          wirePaperPriority(state.selected);
        }
      }
      closeResearch();
    } catch (error) { $("#research-message").textContent = error.message; }
    finally { $("#save-research").disabled = false; }
  };
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeResearch(); });
}
