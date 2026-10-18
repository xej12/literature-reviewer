/* On-demand, evidence-linked chapters. Opening or switching chapters is free. */
const deepViews = new Map();
let activeDeepView = null;

function repairDeepMathWhitespace(latex) {
  // A JSON string can contain a literal backslash-n instead of a newline.
  // Never replace all \\n: that would change valid commands such as \\nu.
  let repaired = latex.replace(/(?<!\\)\\n(?=\s|\\|$)/g, '\n');
  repaired = repaired.replace(/(^|\n)([ \t]*)\\(n[A-Za-z])(?=[_^=({\s]|$)/g, (raw, line, space, command) => {
    try {
      katex.renderToString(`\\${command}`, {throwOnError:true, trust:false});
      return raw; // Preserve valid commands, including \\nu, \\ne and \\ni.
    } catch {
      return line + space + '\n' + command.slice(1);
    }
  });
  return repaired;
}

function deepEquationSource(prefix, block, source) {
  if (!block) return '';
  if (block.basis === 'background') return '<div class="deep-equation-note">补充教学中的公式 · 如引用原式，请对照 PDF 核对</div>';
  const references = [...prefix.matchAll(/(?:公式|式|equation|eq\.?)\s*[（(]\s*([A-Za-z0-9.-]{1,20})\s*[）)]/gi)];
  const last = references.at(-1);
  const number = last && prefix.length - last.index - last[0].length < 180 ? last[1] : '';
  const key = source?.attachmentKey;
  const candidates = (block.sources || []).filter(s => Number.isInteger(s.page) && s.page > 0 && (!source?.pageCount || s.page <= source.pageCount));
  // A matching number is a navigation hint, not a mathematical verification.
  const escapedNumber = number.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  // A list item beginning '(4) explanation' is not an equation label.
  const equationLabel = new RegExp(`[（(]\\s*${escapedNumber}\\s*[）)][^\\S\\r\\n]*(?:\\r?\\n|$)`);
  const matching = number ? candidates.filter(s => equationLabel.test(String(s.text || ''))) : [];
  const pages = [...new Set((matching.length ? matching : candidates).map(s => s.page))].sort((a,b) => a-b);
  const label = number ? `讲解引用：式（${escapeHtml(number)}）` : '讲解中的公式 · 原式编号未明确';
  if (!/^[A-Z0-9]+$/.test(key || '') || !pages.length) return `<div class="deep-equation-note">${label} · 暂无可定位原文，请核对 PDF</div>`;
  return `<details class="deep-equation-source"><summary>${label} · ${matching.length ? '原文编号所在页' : '原文候选页'} ${pages.join('、')} · 展开对照</summary>
    <p class="deep-equation-note">${matching.length ? '根据引用片段中的编号定位，转写的符号与上下标请对照下方原 PDF。' : '尚未定位到确切公式编号，下方是本段引用的原文页，请先核对原式。'}</p>
    <div class="deep-equation-pages">${pages.map(page => `<button type="button" class="secondary-button deep-equation-open" data-key="${key}" data-page="${page}">放大阅读第 ${page} 页</button>`).join('')}</div>
    <div class="deep-equation-images">${pages.map(page => `<figure><figcaption>原 PDF · 第 ${page} 页</figcaption><img data-src="/api/attachments/${key}/page-image?page=${page}" alt="原 PDF 第 ${page} 页，含完整公式及上下文" /></figure>`).join('')}</div>
    </details>`;
}

function renderReadingParagraphs(text, inline) {
  let html = '';
  for (const part of text.trim().split(/\n\s*\n/)) {
    const paragraph = part.trim().replace(/^[，；]\s*/, '');
    if (!paragraph) continue;
    if (/^\uE000\d+\uE001$/.test(paragraph)) { html += inline(paragraph); continue; }
    const lines = paragraph.split('\n').filter(line => line.trim());
    const bullets = lines.map(line => line.match(/^\s*(?:([-*•])|(?:(\d+)[.、）)]))\s+(.+)$/));
    if (bullets.length && bullets.every(Boolean)) {
      const ordered = bullets.every(b => b[2]);
      const tag = ordered ? 'ol' : 'ul';
      html += `<${tag} class="reading-list"${ordered ? ` start="${Number(bullets[0][2])}"` : ''}>${bullets.map(b => `<li>${inline(b[3])}</li>`).join('')}</${tag}>`;
      continue;
    }
    // Old cached answers often have no paragraph breaks. Split at existing
    // sentence boundaries, preserving every word and punctuation mark.
    const sentences = paragraph.length > 220 ? paragraph.split(/(?<=[。！？；])\s*/) : [paragraph];
    let group = '';
    const flush = () => { if (group.trim()) html += `<p class="reading-paragraph">${inline(group.trim()).replace(/\n/g, '<br>')}</p>`; group = ''; };
    for (const sentence of sentences) {
      if (group && group.length + sentence.length > 220) flush();
      group += sentence;
    }
    flush();
  }
  return html;
}

function renderReadingStructure(text, inline) {
  text = text.replace(/(^|[。！？；\s])(?=问\s*\d*\s*[:：])/g, '$1\n\n')
    .replace(/(^|[。；\s])(?=(?:可以支持的?|不能支持的?|可支持的?|不支持的?|成立条件|注意事项)\s*[:：])/g, '$1\n\n')
    .replace(/(^|[。；\s])(?=(?:原文)?(?:公式|式)\s*[（(]\s*[\w.-]+\s*[）)]\s*[:：])/g, '$1\n\n');
  const questions = [...text.matchAll(/(?:^|\n)[ \t]*问\s*(\d*)\s*[:：]/g)];
  if (!questions.length) return renderReadingParagraphs(text, inline);
  let html = renderReadingParagraphs(text.slice(0, questions[0].index), inline);
  questions.forEach((match,i) => {
    const content = text.slice(match.index + match[0].length, questions[i+1]?.index ?? text.length).trim();
    const answer = /(^|[\s？?。])(?:参考答案|答)\s*[:：]/.exec(content);
    const question = answer ? content.slice(0, answer.index + answer[1].length) : content;
    const response = answer ? content.slice(answer.index + answer[0].length) : '';
    html += `<section class="reading-qa"><div class="reading-question"><span class="reading-qa-label">问题${escapeHtml(match[1] || String(i+1))}</span>${renderReadingParagraphs(question, inline)}</div>${answer ? `<div class="reading-answer"><span class="reading-qa-label">参考答案</span>${renderReadingParagraphs(response, inline)}</div>` : ''}</section>`;
  });
  return html;
}

function renderDeepText(value, block = null, source = null) {
  value = String(value || '').replace(/[\uE000\uE001]/g, '');
  const pattern = /(\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$[^$\n]+\$)/g;
  const math = [];
  let text = '', offset = 0;
  for (const match of String(value || "").matchAll(pattern)) {
    const prefix = value.slice(offset, match.index);
    text += prefix;
    const raw = match[0], delimitedDisplay = raw.startsWith('$$') || raw.startsWith('\\[');
    const latex = raw.slice(raw.startsWith('$') && !delimitedDisplay ? 1 : 2, raw.startsWith('$') && !delimitedDisplay ? -1 : -2);
    const namedEquation = /(?:原文)?(?:公式|式)\s*[（(]\s*[\w.-]+\s*[）)]\s*[:：]?\s*$/.test(prefix);
    const relation = /=|\\(?:propto|approx|equiv|sim|leq|geq)\b/.test(latex);
    const display = delimitedDisplay || (relation && (namedEquation || latex.length > 90));
    let rendered;
    try {
      if (!window.katex) throw new Error("Math renderer unavailable");
      const options = {displayMode: display, throwOnError: true, trust: false, strict: "ignore", maxExpand: 1000};
      try { rendered = katex.renderToString(latex, options); }
      catch { rendered = katex.renderToString(repairDeepMathWhitespace(latex), options); }
    } catch {
      rendered = `<code class="deep-math-fallback" title="公式排版未成功，请结合原 PDF 核对">${escapeHtml(raw)}</code>`;
    }
    const token = `\uE000${math.length}\uE001`;
    math.push(display ? `<div class="deep-equation">${rendered}${deepEquationSource(prefix, block, source)}</div>` : rendered);
    text += display ? `\n\n${token}\n\n` : token;
    offset = match.index + raw.length;
  }
  text += value.slice(offset);
  const inline = fragment => escapeHtml(fragment).replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    .replace(/^((?:可以支持的?|不能支持的?|可支持的?|不支持的?|成立条件|注意事项|物理意义|单位)\s*[:：])/, '<strong>$1</strong>')
    .replace(/\uE000(\d+)\uE001/g, (_,index) => math[Number(index)] || '');
  return renderReadingStructure(text, inline);
}

function deepPageRanges(pages = []) {
  const ranges = [];
  for (const page of pages) {
    const last = ranges[ranges.length - 1];
    if (last && page === last[1] + 1) last[1] = page;
    else ranges.push([page, page]);
  }
  return ranges.map(([a, b]) => a === b ? a : `${a}–${b}`).join("、");
}

function deepCoverage(source) {
  if (!source) return "";
  return `<div class="deep-coverage"><strong>正文材料：${source.readablePages.length} / ${source.pageCount} 页可提取文字</strong>
    <span>${source.partial ? `本章使用部分正文片段，涉及第 ${deepPageRanges(source.includedPages)} 页；不保证覆盖全文。` : "本章材料包含所有已提取正文；公式符号和页面排版仍需结合 PDF 核对。"}</span>
    ${source.termFound !== undefined ? `<span class="${source.termFound ? '' : 'deep-warning'}">${source.termFound ? `术语文字匹配涉及第 ${deepPageRanges(source.matchedPages)} 页，本次材料含其中第 ${deepPageRanges(source.includedMatchedPages)} 页；词面匹配仅供定位。` : '未在提取文字中直接检索到该术语，可能有缩写、断词或提取问题；讲解必须区分背景知识与本文事实。'}</span>` : ''}
    ${source.emptyPages.length ? `<span class="deep-warning">第 ${deepPageRanges(source.emptyPages)} 页未提取出文字，可能包含图像或扫描内容。</span>` : ""}</div>`;
}

function deepSources(block, source) {
  const key = source?.attachmentKey;
  const validKey = typeof key === "string" && /^[A-Z0-9]+$/.test(key);
  return `<details class="deep-sources"><summary>${block.sources?.length ? `查看原文依据 · ${block.sources.length} 处` : "未提供可定位的原文依据"}</summary>
    ${(block.sources || []).map(s => `<div class="deep-excerpt">${validKey && Number.isInteger(s.page) && s.page > 0 ? `<a href="/api/attachments/${key}/file#page=${s.page}" target="_blank" rel="noopener">打开 PDF 第 ${s.page} 页 ↗</a>` : "原文片段"}<blockquote>${escapeHtml(s.text)}</blockquote></div>`).join("")}
    <p class="deep-citation-note">定位经过编号匹配；是否支持上方解释，请结合原文核对。</p></details>`;
}

function paintDeepReading(view) {
  if (activeDeepView !== view || $("#analysis-modal").classList.contains("hidden") || !$("#analysis-modal").classList.contains("deep-modal")) return;
  const panel = $("#analysis-modal-body"), data = view.data;
  const isTerm = view.kind === 'term';
  const unit = isTerm ? '个术语' : '章';
  const legacy = isTerm ? null : view.item.analysis?.summary;
  const versions = data.versions || [];
  const reading = view.archive >= 0 ? versions[view.archive] : data.reading;
  const currentChapter = reading?.sections?.[view.section];
  const draft = reading?.drafts?.[view.section];
  const draftHasText = Boolean(draft?.content?.trim());
  const noAnswer = Boolean(draft && !draftHasText);
  const history = reading?.history?.[view.section] || [];
  const chapter = view.revision >= 0 ? history[view.revision] : currentChapter;
  const isLegacy = view.section === "legacy";
  const chapterInfo = data.chapters.find(c => c.id === view.section);
  const source = chapter?.coverage || draft?.coverage || data.sources?.[view.section] || data.source;
  const basisLabels = {paper: "论文原文", background: "补充背景 / 教学示例", inference: "分析推断 / 建议"};
  const completed = Object.keys(reading?.sections || {}).length;
  const disabled = Boolean(view.pending) || view.archive >= 0 || view.revision >= 0 || !data.source || (isTerm && !chapterInfo);
  const archived = view.archive >= 0;
  panel.innerHTML = `<div class="deep-layout${isTerm ? ' term-reading-layout' : ''}"><nav class="deep-nav" aria-label="${isTerm ? '专业术语' : '论文解读章节'}">
    <div class="deep-nav-title">${isTerm ? '逐个讲透专业术语' : '按章节理解论文'}</div><p>已保存 ${completed} / ${data.chapters.length} ${unit}</p>
    ${isTerm ? `<form id="term-focus-form" class="term-focus-form"><label for="term-focus">输入想理解的术语</label><input id="term-focus" maxlength="150" placeholder="如 coronagraph" required /><button class="secondary-button" ${view.pending ? 'disabled' : ''}>打开术语（免费）</button></form>` : ''}
    ${data.chapters.map((c, i) => `<button class="deep-chapter" data-section="${c.id}" aria-current="${view.section === c.id ? "page" : "false"}"><span>${String(i + 1).padStart(2, "0")} ${escapeHtml(c.title)}</span><small>${view.pending === c.id ? "正在处理…" : reading?.drafts?.[c.id] ? reading.drafts[c.id].content?.trim() ? "答复已保存 · 待整理" : "未生成正文" : reading?.sections?.[c.id] ? "已保存" : "按需生成"}</small></button>`).join("")}
    ${legacy ? `<button class="deep-chapter" data-section="legacy" aria-current="${isLegacy ? "page" : "false"}"><span>旧版解读</span><small>原结果保留</small></button>` : ""}
    ${versions.length ? `<label class="deep-version-label" for="deep-version">材料版本</label><select id="deep-version"><option value="-1">当前 PDF</option>${versions.map((v, i) => `<option value="${i}" ${view.archive === i ? "selected" : ""}>已存版本 ${i + 1}${v.fingerprint === data.reading?.fingerprint ? " · 当前材料" : " · 旧材料"}</option>`).join("")}</select>` : ""}
    <p class="deep-free-note">${isTerm ? '打开和切换术语免费。每个术语单独生成、保存；原有短定义仍保留。' : '打开和切换章节免费。只有点击生成时才调用模型；结果按文献保存。'}</p>
    </nav><main class="deep-document" tabindex="-1"><div class="deep-paper-title">${escapeHtml(view.item.title)}</div>
    ${view.error ? `<div role="alert" class="analysis-error">${escapeHtml(view.error)}</div>` : ""}
    ${isLegacy ? `<div class="deep-chapter-heading"><h3>旧版论文解读</h3><span>已保存 · 不消耗 Token</span></div>${Object.entries({research_question: "研究问题", methods: "方法与数据", findings: "主要发现", limitations: "局限性"}).map(([key, title]) => `<section class="deep-block"><h4>${title}</h4><div class="deep-prose">${escapeHtml(legacy?.[key] || "原文未说明")}</div></section>`).join("")}` : `
    <div class="deep-chapter-heading"><h3>${escapeHtml(chapterInfo?.title || (isTerm ? '选一个术语开始' : '论文解读'))}</h3><span>${archived ? "已存版本 · 只读" : noAnswer ? "未生成正文" : draft ? "答复已保存 · 待整理" : chapter ? "已保存 · 打开免费" : "尚未生成"}</span></div>
    ${history.length ? `<label class="deep-revision-label">章节记录 <select id="deep-revision"><option value="-1">最新结果</option>${history.map((h, i) => `<option value="${i}" ${view.revision === i ? "selected" : ""}>历史结果 ${i + 1} · ${escapeHtml(h.generatedAt || "已保存")}</option>`).join("")}</select></label>` : ""}
    ${archived ? `<div class="deep-warning deep-notice">正在查看已存材料版本；如果 PDF 已更换，下面的旧页码可能不再对应当前文件。</div>` : ""}
    ${data.sourceError ? `<div class="deep-warning deep-notice">${escapeHtml(data.sourceError)}</div>` : ""}
    ${deepCoverage(source)}
    <div class="deep-toolbar"><button id="deep-generate" class="primary-button" ${disabled ? "disabled" : ""}>${isTerm ? view.pending === view.section ? '正在讲解本术语…' : chapter || draft ? '重新生成讲解（消耗 Token）' : '讲透这个术语（消耗 Token）' : view.pending === view.section ? "正在处理本章…" : chapter || draft ? "重新生成本章（消耗 Token）" : "生成本章（消耗 Token）"}</button><button id="deep-settings" class="text-button">生成设置</button><span>${view.pending ? "模型正在生成，关闭此窗口会取消本次请求。" : isTerm ? '只讲当前术语，不会自动生成其他术语。' : "各章独立保存，无需一次生成全部内容。"}</span></div>
    <p class="deep-budget">${escapeHtml(state.model?.generation?.budgetLabel || "输出预算跟随模型服务默认值")}${state.model?.generation?.thinkingLabel ? ` · ${escapeHtml(state.model.generation.thinkingLabel)}` : ""}</p>
    ${draft ? `<section class="deep-draft"><strong>${noAnswer ? "本次未生成正文，已保留请求状态" : "本次答复已保存在本电脑，暂未作为完整章节采用"}</strong><p>${escapeHtml(noAnswer && draft.finishReason === "length" ? "模型在输出正文前耗尽了本次预算。思考模式也会占用预算；本工具现已取消旧的 8000 固定限制，重新生成会使用上方当前设置。" : draft.formatError || "答复等待本地整理。")}</p>${!disabled && draftHasText ? `<button id="deep-recover" class="secondary-button">重新整理已存答复（免费）</button>` : ""}${draftHasText ? `<details><summary>查看已保存答复（免费）</summary><pre>${escapeHtml(draft.content)}</pre></details>` : `<p>没有正文可供本地整理，需要重新生成。不会自动调用模型。</p>`}${draft.usage?.completionTokens !== undefined ? `<p>本次输出用量 ${escapeHtml(draft.usage.completionTokens)} Token${draft.usage.reasoningTokens !== undefined ? `，其中思考用量 ${escapeHtml(draft.usage.reasoningTokens)} Token` : ""}。</p>` : ""}${chapter ? `<p>下方继续显示上一次成功生成的章节。</p>` : ""}</section>` : ""}
    ${chapter ? `<p class="deep-intro">${escapeHtml(chapter.intro)}</p>
      ${(chapter.notices || []).map(n => `<p class="deep-warning">${escapeHtml(n)}</p>`).join("")}
      ${chapter.blocks.map((b, i) => `<section class="deep-block"><div class="deep-block-heading"><h4>${i + 1}. ${escapeHtml(b.title)}</h4><span class="deep-basis ${b.basis}">${escapeHtml(basisLabels[b.basis] || "待核对")}${b.unverified ? " · 定位待核对" : ""}</span></div><div class="deep-prose">${renderDeepText(b.body, b, source)}</div>${deepSources(b, source)}</section>`).join("")}
      <p class="deep-saved">已保存于 ${escapeHtml(chapter.generatedAt || "本电脑")} · 模型 ${escapeHtml(chapter.model || "未记录")}</p>` : draft ? "" : `<div class="deep-empty"><h4>${escapeHtml(chapterInfo?.title || (isTerm ? '术语精讲' : '本章'))}会解释什么？</h4><p>${escapeHtml(isTerm ? '专业译名与含义 → 必要基础 → 工作机制 → 在本文中的作用 → 教学例子与必要公式 → 易混淆概念与局限 → 自检题和参考答案。论文事实与补充教学分开，提供可定位的原文依据。' : deepChapterDescriptions[view.section] || "")}</p><p>${isTerm ? '输入一个术语或从左侧选择，再点“讲透这个术语”才会调用模型。' : '点击上方“生成本章”开始。已有的其他章节和旧版解读会保留。'}</p></div>`}`}
    </main></div>`;
  panel.querySelectorAll(".deep-chapter").forEach(button => button.onclick = () => {
    view.section = button.dataset.section; view.revision = -1; view.error = ""; paintDeepReading(view);
  });
  $("#deep-version")?.addEventListener("change", event => { view.archive = Number(event.target.value); view.revision = -1; view.error = ""; paintDeepReading(view); });
  $("#deep-revision")?.addEventListener("change", event => { view.revision = Number(event.target.value); view.error = ""; paintDeepReading(view); });
  $("#deep-generate")?.addEventListener("click", () => runDeepChapter(view));
  $("#deep-recover")?.addEventListener("click", () => runDeepChapter(view, true));
  $("#deep-settings")?.addEventListener("click", openSettings);
  $('#term-focus-form')?.addEventListener('submit', event => {
    event.preventDefault();openTermReading(view.item, $('#term-focus').value);
  });
  const readingPdf = view.item.attachments?.find(a => a.exists && attachmentTypeLabel(a) === 'PDF');
  panel.querySelectorAll('.deep-equation-source').forEach(details => details.addEventListener('toggle', () => {
    if (details.open) details.querySelectorAll('img[data-src]').forEach(img => {
      img.onerror = () => { img.hidden = true; const message = document.createElement('p'); message.className = 'deep-warning'; message.textContent = '原文预览加载失败，请点击上方按钮打开 PDF。'; img.after(message); };
      img.src = img.dataset.src; delete img.dataset.src;
    });
  }));
  panel.querySelectorAll('.deep-equation-open').forEach(button => button.onclick = () => {
    const pdf = view.item.attachments?.find(a => a.key === button.dataset.key && a.exists);
    if (pdf) openSelectionReader(view.item, pdf, Number(button.dataset.page));
    else window.open(`/api/attachments/${button.dataset.key}/file#page=${button.dataset.page}`, '_blank', 'noopener');
  });
  if (readingPdf) {
    const button = document.createElement('button');
    button.id = 'deep-selection-reader';button.className = 'text-button';button.textContent = '划词阅读原文';
    button.onclick = () => openSelectionReader(view.item, readingPdf);
    panel.querySelector('.deep-toolbar')?.append(button);
  }
}

const deepChapterDescriptions = {
  overview: "补齐本文必需的背景，解释已有方法遇到的具体问题、本文的核心直觉，以及接下来该怎样读。",
  methods: "沿真实方法逐步解释输入、操作、输出、为什么需要这一步、关键假设，并用教学例子串起流程。",
  formulas: "解释关键公式的符号、单位、物理意义、成立条件和必要推导。提取不完整的公式会指出原文位置，供你核对。",
  evidence: "逐项连接研究问题、实验设计、比较条件、指标与结果，解释每个结论有哪些支持和边界。",
  limits: "找出关键假设和失效条件，并用针对本文的问题与参考答案检查自己是否理解。",
};

async function openDeepReading(item) {
  openAnalysis("论文深度解读", "DEEP READING");
  let view = deepViews.get(item.key);
  const firstOpen = !view;
  if (!view) {
    view = {item, section: "overview", archive: -1, revision: -1, pending: null, error: "", data: null};
    deepViews.set(item.key, view);
  }
  view.item = item;
  activeDeepView = view;
  if (view.data) paintDeepReading(view);
  if (view.pending && view.data) return;
  try {
    // Refresh source identity without making any model request.
    view.data = await getJson(`/api/items/${item.key}/deep-reading`);
    if (firstOpen) view.section = Object.keys(view.data.reading?.drafts || {})[0] || Object.keys(view.data.reading?.sections || {})[0] || "overview";
    paintDeepReading(view);
  } catch (error) {
    view.error = error.message;
    if (view.data) paintDeepReading(view);
    else if (activeDeepView === view && $("#analysis-modal").classList.contains("deep-modal")) {
      $("#analysis-modal-body").innerHTML = `<div class="analysis-error">${escapeHtml(error.message)}</div>`;
    }
  }
}

async function runDeepChapter(view, recoverOnly = false) {
  if (view.pending || view.archive >= 0 || view.revision >= 0 || !view.data.source) return;
  const section = view.section, existing = view.data.reading?.sections?.[section], draft = view.data.reading?.drafts?.[section];
  if (!recoverOnly && (existing || draft) && !window.confirm(view.kind === 'term' ? '重新生成本术语讲解会消耗 Token，已保存结果仍会保留。继续吗？' : "重新生成本章会消耗 Token，已保存结果仍会保留。继续吗？")) return;
  view.pending = section; view.error = ""; paintDeepReading(view);
  const request = beginAnalysisGeneration(() => { view.pending = null; view.error = '本次生成已取消，已有结果保留。'; });
  view.generationRequest = request;
  try {
    const isTerm = view.kind === 'term';
    const term = view.data.chapters.find(c => c.id === section)?.term;
    const result = await postJson(`/api/items/${view.item.key}/${isTerm ? 'term-reading' : 'deep-reading'}`, {...(isTerm ? {term} : {section}), force: !recoverOnly && Boolean(existing || draft), repairOnly: recoverOnly}, request.options);
    if (request.cancelled || view.generationRequest !== request) return;
    view.data.reading = result.reading;
    const versionIndex = view.data.versions.findIndex(v => v.fingerprint === result.reading.fingerprint && v.schemaVersion === result.reading.schemaVersion);
    if (versionIndex >= 0) view.data.versions[versionIndex] = result.reading;
    else view.data.versions.push(result.reading);
    if (!isTerm) view.item.analysis = {...(view.item.analysis || {}), deepReadingAvailable: true};
    if (!isTerm && state.selected?.key === view.item.key) {
      state.selected.analysis = {...(state.selected.analysis || {}), deepReadingAvailable: true};
      const button = $("#analyze-summary");
      if (button) button.textContent = "查看论文解读";
    }
    loadItems({quiet: true});
  } catch (error) {
    if (request.cancelled || error.name === 'AbortError' || view.generationRequest !== request) return;
    view.error = error.message || String(error);
  } finally {
    finishAnalysisGeneration(request);
    if (view.generationRequest === request) { view.pending = null; paintDeepReading(view); }
  }
}
