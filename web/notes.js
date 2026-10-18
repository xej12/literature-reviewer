/* Private, human-written notes. No model endpoints are used here. */
const noteMarkdown = new markdownit({html:false, breaks:true, linkify:false});
function noteMath(latex, display, env = {}) {
  try { return katex.renderToString(latex, {displayMode:display, throwOnError:false, trust:false, maxExpand:1000, output:env.export ? 'mathml' : 'htmlAndMathml'}); }
  catch { return `<code>${escapeHtml(latex)}</code>`; }
}
noteMarkdown.inline.ruler.before('escape', 'note_math', (s, silent) => {
  if (s.src[s.pos] !== '$' || s.src[s.pos+1] === '$') return false;
  let end = s.pos+1;
  while ((end = s.src.indexOf('$', end)) >= 0 && s.src[end-1] === '\\') end++;
  if (end < 0 || !s.src.slice(s.pos+1,end).trim() || s.src.slice(s.pos+1,end).includes('\n')) return false;
  if (!silent) { const token=s.push('note_math_inline','math',0); token.content=s.src.slice(s.pos+1,end); }
  s.pos=end+1; return true;
});
noteMarkdown.block.ruler.before('fence','note_math_block',(s,start,end,silent) => {
  const line=s.src.slice(s.bMarks[start]+s.tShift[start],s.eMarks[start]);
  if (!line.startsWith('$$')) return false;
  let last=start, content=line.slice(2), close=content.indexOf('$$');
  if (close >= 0) { if (content.slice(close+2).trim()) return false; content=content.slice(0,close); }
  else {
    const parts=[content]; let found=false;
    for (last=start+1; last<end; last++) {
      const next=s.src.slice(s.bMarks[last]+s.tShift[last],s.eMarks[last]), at=next.indexOf('$$');
      if (at>=0 && !next.slice(at+2).trim()) { parts.push(next.slice(0,at)); found=true; break; }
      parts.push(next);
    }
    if (!found) return false;
    content=parts.join('\n');
  }
  if (silent) return true;
  const token=s.push('note_math_block','math',0); token.content=content; token.map=[start,last+1]; token.block=true;
  s.line=last+1; return true;
});
noteMarkdown.renderer.rules.note_math_inline=(tokens,i,options,env)=>noteMath(tokens[i].content,false,env);
noteMarkdown.renderer.rules.note_math_block=(tokens,i,options,env)=>`<div class="note-math">${noteMath(tokens[i].content,true,env)}</div>\n`;
// Do not fetch external images or local API URLs just by previewing a note.
noteMarkdown.renderer.rules.image=(tokens,i)=>`<span class="note-image-placeholder">[图片引用：${escapeHtml(tokens[i].content || '图片')}；本版不自动加载]</span>`;
noteMarkdown.renderer.rules.link_open=(tokens,i,options,env,self)=>{
  tokens[i].attrSet('target','_blank'); tokens[i].attrSet('rel','noopener noreferrer');
  return self.renderToken(tokens,i,options);
};
function renderNoteMarkdown(text, exported=false) { return noteMarkdown.render(text || '', {export:exported}); }

const notebook = {notes:[], templates:[], current:null, paper:null, query:'', active:false, timer:null, inFlight:null, routeRequest:0, sidebarRequest:0};
const noteTime=value=>new Date(value).toLocaleString('zh-CN',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
function noteMessage(message='') { const el=$('#notes-message'); el.textContent=message; el.classList.toggle('hidden',!message); }
function noteStatus(message, failed=false) { const el=$('#note-save-status'); if(el){el.textContent=message;el.classList.toggle('failed',failed);} }
function noteDraftKey(id) { return `literature-reviewer:note:${id}`; }
function keepNoteDraft(current) {
  try { localStorage.setItem(noteDraftKey(current.note.id), JSON.stringify({title:current.note.title,body:current.note.body,revision:current.note.revision})); return true; }
  catch { noteStatus('浏览器草稿不可用，请立即保存或导出',true); return false; }
}
function forgetNoteDraft(id) { try { localStorage.removeItem(noteDraftKey(id)); } catch {} }
function noteHash(id='', paper=notebook.paper) { return `#/notes${id ? '/'+id : ''}${paper ? '?paper='+encodeURIComponent(paper.key) : ''}`; }
function navigateNotes(hash) { history.pushState(null,'',hash); applyRoute(); }

async function refreshNoteSidebar() {
  const request=++notebook.sidebarRequest, result=await getJson('/api/notes');
  if(request!==notebook.sidebarRequest)return;
  $('#notes-count').textContent=result.total;
  $('#recent-notes').innerHTML=result.notes.slice(0,3).map(n=>`<button class="recent-note" data-note-id="${n.id}"><span>${escapeHtml(n.title)}</span><small>${escapeHtml(noteTime(n.updatedAt))}</small></button>`).join('') || '<p class="sidebar-empty">把读过的内容，变成自己的理解。</p>';
  $('#recent-notes').querySelectorAll('button').forEach(b=>b.onclick=()=>navigateNotes(`#/notes/${b.dataset.noteId}`));
}
async function refreshNoteList() {
  const request=notebook.listRequest=(notebook.listRequest || 0)+1;
  const params=new URLSearchParams(); if(notebook.query)params.set('q',notebook.query); if(notebook.paper)params.set('itemKey',notebook.paper.key);
  const scope=`${notebook.query}|${notebook.paper?.key || ''}`, result=await getJson('/api/notes?'+params);
  if(request!==notebook.listRequest || scope!==`${notebook.query}|${notebook.paper?.key || ''}`)return;
  notebook.notes=result.notes;
  $('#notes-filter').innerHTML=notebook.paper ? `<p>当前文献的笔记 <button id="notes-all" class="text-button">查看全部</button></p>` : `<p>${result.total} 篇笔记 · 最近修改优先</p>`;
  $('#notes-all')?.addEventListener('click',()=>navigateNotes('#/notes'));
  $('#notes-list').innerHTML=result.notes.map(n=>`<button class="notebook-card ${notebook.current?.note.id===n.id?'selected':''}" data-note-id="${n.id}"><strong>${escapeHtml(n.title)}</strong><span>${escapeHtml(n.excerpt || '空白笔记，等待写下你的想法')}</span><small>${n.paper?'关联文献 · ':''}${escapeHtml(noteTime(n.updatedAt))}</small></button>`).join('') || `<p class="notes-list-empty">${notebook.query?'没有匹配的笔记，试试其他关键词。':'还没有笔记。选一个模板，写下第一个想法。'}</p>`;
  $('#notes-list').querySelectorAll('button').forEach(b=>b.onclick=()=>navigateNotes(noteHash(b.dataset.noteId)));
  if(result.unreadable)noteMessage(`${result.unreadable} 个笔记文件无法读取，已保留原文件，请检查备份。`);
}
function templatePicker() {
  $('#note-editor-panel').innerHTML=`<div class="note-start"><span class="note-start-mark">✎</span><h3>从一个问题开始记</h3><p>${notebook.paper ? `关联文献：${escapeHtml(notebook.paper.title)}` : '选择一个模板。模板只是问题提纲，内容由你自己掌握。'}</p><div class="note-template-grid">${notebook.templates.map(t=>`<button class="note-template" data-template="${escapeHtml(t.id)}"><strong>${escapeHtml(t.name)}</strong><span>${escapeHtml(t.description)}</span><small>使用此模板 →</small></button>`).join('')}</div><p class="note-local-hint">笔记保存在本电脑 · 不调用模型 · 不修改 Zotero 原库</p></div>`;
  $('#note-editor-panel').querySelectorAll('[data-template]').forEach(button=>button.onclick=async()=>{
    $('#note-editor-panel').querySelectorAll('button').forEach(b=>b.disabled=true);
    try { const note=await postJson('/api/notes',{template:button.dataset.template,itemKey:notebook.paper?.key || ''}); refreshNoteSidebar().catch(()=>{}); navigateNotes(noteHash(note.id)); }
    catch(error){noteMessage(error.message);$('#note-editor-panel').querySelectorAll('button').forEach(b=>b.disabled=false);}
  });
}
function updateNotePreview() {
  if(!notebook.current)return;
  $('#note-preview').innerHTML=renderNoteMarkdown(notebook.current.note.body) || '<p class="note-preview-empty">这里会显示排版后的笔记。</p>';
  $('#note-word-count').textContent=`${notebook.current.note.body.length.toLocaleString()} 字符`;
}
function changeNote() {
  const current=notebook.current; if(!current)return;
  current.note.title=$('#note-title').value;current.note.body=$('#note-body').value;current.dirty=true;
  const protectedDraft=keepNoteDraft(current);noteStatus(protectedDraft?'未保存 · 正在等待自动保存':'浏览器草稿不可用，请立即保存或导出',!protectedDraft);updateNotePreview();
  clearTimeout(notebook.timer);notebook.timer=setTimeout(()=>saveNote(),700);
}
async function saveNote() {
  clearTimeout(notebook.timer);
  if(notebook.current?.deleting)return false;
  if(notebook.inFlight) { await notebook.inFlight; if(notebook.current?.dirty && !notebook.current.error)return saveNote();return !notebook.current?.dirty; }
  const current=notebook.current;
  if(!current?.dirty)return true;
  const snapshot={title:current.note.title,body:current.note.body,revision:current.note.revision};
  current.error=false;noteStatus('正在保存…');
  notebook.inFlight=(async()=>{
    try {
      const saved=await postJson(`/api/notes/${current.note.id}`,snapshot);
      current.note.revision=saved.revision;current.note.updatedAt=saved.updatedAt;
      current.dirty=current.note.title!==snapshot.title || current.note.body!==snapshot.body;
      if(current.dirty)keepNoteDraft(current);else forgetNoteDraft(current.note.id);
      noteStatus(current.dirty?'还有新内容待保存':`已保存到本电脑 · ${noteTime(saved.updatedAt)}`);
      if(!current.deleting){refreshNoteSidebar().catch(()=>{});refreshNoteList().catch(()=>{});}
      return true;
    } catch(error) {
      current.error=true;const protectedDraft=keepNoteDraft(current);noteStatus(`保存失败：${error.message}${protectedDraft?'':' 浏览器草稿也不可用，请立即导出。'}`,true);return false;
    }
  })();
  const success=await notebook.inFlight;notebook.inFlight=null;
  if(success && current.dirty)return saveNote();
  return success;
}
function insertNoteSyntax(before,after='',placeholder='内容') {
  const editor=$('#note-body'),start=editor.selectionStart,end=editor.selectionEnd,text=editor.value.slice(start,end)||placeholder;
  editor.setRangeText(before+text+after,start,end,'end');editor.focus();changeNote();
}
function noteExportMarkdown(note) {
  const line=value=>String(value || '').replace(/[\r\n]+/g,' '),paper=note.paper;
  const metadata=paper ? `关联文献：${line(paper.title)}\n\n作者：${line((paper.creators || []).join('；'))}\n\n来源：${line(paper.publicationTitle)} ${line(paper.date)}\n\n${paper.doi ? 'DOI：'+line(paper.doi)+'\n\n' : ''}Zotero 条目键：${line(paper.key)}\n\n` : '';
  return `# ${line(note.title)||'未命名笔记'}\n\n${metadata}${note.body}\n`;
}
function noteExportHtml(note) {
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>${escapeHtml(note.title)}</title><style>body{max-width:850px;margin:40px auto;padding:0 26px;font-family:system-ui,'Microsoft YaHei',sans-serif;line-height:1.9;color:#253347;overflow-wrap:anywhere}h1{font-size:28px}h2{margin-top:2em;border-bottom:1px solid #ddd;padding-bottom:.3em}h3{margin-top:1.6em}blockquote{border-left:3px solid #a4b2d6;margin-left:0;padding-left:18px;color:#657286}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:8px;text-align:left}pre{white-space:pre-wrap;background:#f4f5f7;padding:15px}code{font-family:monospace}math[display=block]{display:block;margin:20px 0;overflow-wrap:normal}.note-math{overflow-x:auto;margin:20px 0}.note-image-placeholder{color:#78859a}@media print{body{max-width:none;margin:0;padding:0}h1,h2,h3{break-after:avoid}pre,tr,blockquote{break-inside:avoid}a{color:inherit}}@page{margin:18mm}</style></head><body>${renderNoteMarkdown(noteExportMarkdown(note),true)}</body></html>`;
}
function downloadNote() {
  const note=notebook.current?.note;if(!note)return;
  const format=$('#note-export-format').value, content=format==='html'?noteExportHtml(note):noteExportMarkdown(note);
  const blob=new Blob([content],{type:format==='html'?'text/html;charset=utf-8':'text/markdown;charset=utf-8'}),url=URL.createObjectURL(blob),link=document.createElement('a');
  link.href=url;link.download=(note.title || '我的笔记').replace(/[<>:"/\\|?*\x00-\x1f]/g,'_').slice(0,100)+'.'+format;
  link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function deleteCurrentNote() {
  const current=notebook.current;
  if(!current || current.deleting)return;
  if(!confirm(`删除笔记“${current.note.title || '未命名笔记'}”？\n\n正文和未保存草稿将被删除，无法在应用内恢复。需要的内容请先导出。`))return;
  current.deleting=true;clearTimeout(notebook.timer);notebook.listRequest=(notebook.listRequest || 0)+1;notebook.sidebarRequest++;
  const controls=[...$('#note-editor-panel').querySelectorAll('input,textarea,button,select')];
  controls.forEach(el=>{el.dataset.deleteDisabled=String(el.disabled);el.disabled=true;});noteStatus('正在删除笔记…');
  if(notebook.inFlight)await notebook.inFlight;
  try {
    await postJson(`/api/notes/${current.note.id}/delete`,{revision:current.note.revision});
    forgetNoteDraft(current.note.id);notebook.current=null;
    navigateNotes(noteHash());refreshNoteSidebar().catch(()=>{});
  } catch(error) {
    current.deleting=false;controls.forEach(el=>{el.disabled=el.dataset.deleteDisabled==='true';delete el.dataset.deleteDisabled;});
    noteStatus(`删除失败：${error.message}`,true);
  }
}
function renderNoteEditor(current) {
  const note=current.note;
  $('#note-editor-panel').innerHTML=`<div class="note-editor-top"><span class="note-template-label">${escapeHtml(notebook.templates.find(t=>t.id===note.template)?.name || '笔记')}</span><div class="note-export-actions"><label class="sr-only" for="note-export-format">导出格式</label><select id="note-export-format"><option value="md">Markdown (.md)</option><option value="html">网页 (.html)</option></select><button id="note-export" class="secondary-button">导出</button><button id="note-print" class="text-button">打印 / 存为 PDF</button></div></div><label class="sr-only" for="note-title">笔记标题</label><input id="note-title" class="note-title" maxlength="200" placeholder="给这篇笔记起个标题" />${note.paper ? `<div class="note-paper-link"><span>关联文献：${escapeHtml(note.paper.title)}</span><button id="note-open-paper" class="text-button">打开文献 ↗</button></div>` : '<p class="note-unlinked">独立笔记 · 也可以从文献详情新建关联笔记</p>'}<div class="note-save-row"><span id="note-save-status" role="status"></span><button id="note-save" class="text-button">立即保存</button><button id="note-reload" class="text-button">载入已存版本</button></div><div class="note-format-bar" aria-label="插入格式"><button data-syntax="heading">标题</button><button data-syntax="bold">粗体</button><button data-syntax="list">列表</button><button data-syntax="quote">引文</button><button data-syntax="formula">公式</button><div class="note-view-tabs" role="group" aria-label="编辑视图"><button data-view="edit" aria-pressed="true">编辑</button><button data-view="split" aria-pressed="false">对照</button><button data-view="preview" aria-pressed="false">预览</button></div></div><div id="note-writing" class="note-writing" data-view="edit"><label class="sr-only" for="note-body">笔记正文（Markdown）</label><textarea id="note-body" maxlength="200000" spellcheck="false" placeholder="写下你自己的理解…"></textarea><article id="note-preview" class="note-prose" aria-label="笔记预览"></article></div><div class="note-editor-footer"><span id="note-word-count"></span><span>自动保存 · Ctrl / ⌘ + S 保存 · 不调用模型</span></div>`;
  $('#note-title').value=note.title;$('#note-body').value=note.body;updateNotePreview();
  $('.note-export-actions').insertAdjacentHTML('beforeend','<button id="note-delete" class="text-button note-delete">删除笔记</button>');
  $('#note-delete').onclick=deleteCurrentNote;
  $('#note-editor-panel').insertAdjacentHTML('beforeend','<details class="note-format-help"><summary>格式与导出说明</summary><p>用上方按钮插入标题、粗体、列表和引文，点“预览”查看排版。行内公式用 $...$，独立公式用两行 $$ 包住。模板里的提示文字可以直接改写或删除。</p><p>Markdown 适合继续编辑；HTML 可以离线打开。点击“打印 / 存为 PDF”，在浏览器打印窗口选择“另存为 PDF”。本版暂不支持图片附件与自定义模板；Markdown 图片引用不会自动加载。</p></details>');
  noteStatus(current.dirty?'已恢复浏览器草稿 · 等待保存':`已保存到本电脑 · ${noteTime(note.updatedAt)}`);
  $('#note-title').addEventListener('input',changeNote);$('#note-body').addEventListener('input',changeNote);
  $('#note-save').onclick=()=>saveNote();$('#note-export').onclick=downloadNote;
  $('#note-reload').onclick=async()=>{
    if(current.dirty && !confirm('载入已存版本会放弃当前未保存草稿。需要的内容请先导出。继续吗？'))return;
    clearTimeout(notebook.timer);if(notebook.inFlight)await notebook.inFlight;
    try { const saved=await getJson('/api/notes/'+note.id);forgetNoteDraft(note.id);notebook.current={note:saved,dirty:false,error:false};renderNoteEditor(notebook.current); }
    catch(error){noteStatus(error.message,true);}
  };
  $('#note-print').onclick=()=>{
    const popup=window.open('','_blank');if(!popup){noteStatus('浏览器阻止了打印窗口，请允许弹窗或导出 HTML 后打印。',true);return;}
    popup.opener=null;popup.document.write(noteExportHtml(notebook.current.note));popup.document.close();setTimeout(()=>{popup.focus();popup.print();},300);
  };
  $('#note-open-paper')?.addEventListener('click',()=>selectItem(note.paper.key));
  const syntax={heading:['\n## ','','小标题'],bold:['**','**','重点'],list:['\n- ','','要点'],quote:['\n> ','','原文摘录（请标页码）'],formula:['\n$$\n','\n$$\n','E = mc^2']};
  document.querySelectorAll('[data-syntax]').forEach(b=>b.onclick=()=>insertNoteSyntax(...syntax[b.dataset.syntax]));
  document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{
    $('#note-writing').dataset.view=b.dataset.view;document.querySelectorAll('[data-view]').forEach(el=>{if(el.tagName==='BUTTON')el.setAttribute('aria-pressed',String(el===b));});
  });
}
async function noteRoute() {
  notebook.active=true;noteMessage('');
  const request=++notebook.routeRequest,url=new URL(location.hash.slice(1),location.origin),id=url.pathname.match(/^\/notes\/([a-f0-9]{32})$/)?.[1],paperKey=url.searchParams.get('paper');
  try {
    if(!notebook.templates.length)notebook.templates=(await getJson('/api/note-templates')).templates;
    if(request!==notebook.routeRequest)return;
    if(paperKey && notebook.paper?.key!==paperKey)notebook.paper=await getJson('/api/items/'+encodeURIComponent(paperKey));
    else if(!paperKey)notebook.paper=null;
    if(request!==notebook.routeRequest)return;
    if(!id){notebook.current=null;templatePicker();}
    else if(notebook.current?.note.id!==id){
      $('#note-editor-panel').innerHTML='<p class="note-loading">正在打开笔记…</p>';
      const note=await getJson('/api/notes/'+id);if(request!==notebook.routeRequest)return;
      const current={note,dirty:false,error:false};let draft;
      try {draft=JSON.parse(localStorage.getItem(noteDraftKey(id)) || 'null');}catch{}
      if(draft && typeof draft.body==='string' && typeof draft.title==='string' && (draft.body!==note.body || draft.title!==note.title)) {
        current.note={...note,title:draft.title,body:draft.body,revision:draft.revision};current.dirty=true;
        current.error=draft.revision!==note.revision;
      }
      notebook.current=current;renderNoteEditor(current);
      if(current.error)noteStatus('浏览器草稿与已存版本有冲突，请先导出草稿，再载入已存版本。',true);
      else if(current.dirty)notebook.timer=setTimeout(()=>saveNote(),700);
    } else renderNoteEditor(notebook.current);
    await refreshNoteList();await refreshNoteSidebar();
  }catch(error){noteMessage(error.message);}
}
window.notesWorkspace={
  init(){
    $('#nav-library').onclick=()=>navigateNotes('#/library');$('#nav-notes').onclick=()=>navigateNotes('#/notes');
    $('#notes-new').onclick=()=>navigateNotes(noteHash());$('#sidebar-new-note').onclick=()=>navigateNotes('#/notes');
    $('#notes-search').oninput=event=>{notebook.query=event.target.value.trim();refreshNoteList().catch(error=>noteMessage(error.message));};
    refreshNoteSidebar().catch(()=>{$('#notes-count').textContent='—';});
    window.addEventListener('beforeunload',event=>{if(notebook.current?.dirty){keepNoteDraft(notebook.current);event.preventDefault();event.returnValue='';}});
    document.addEventListener('keydown',event=>{if(notebook.active && (event.ctrlKey || event.metaKey) && event.key.toLowerCase()==='s'){event.preventDefault();saveNote();}});
  },
  route:noteRoute,
  flush:()=>saveNote(),
  keepRoute(){if(notebook.current)history.replaceState(null,'',noteHash(notebook.current.note.id));},
  leave(){notebook.active=false;notebook.routeRequest++;},
  forPaper(item){notebook.paper=item;navigateNotes(noteHash('',item));}
};
