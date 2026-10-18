/* Explicit, cached multi-paper searches. No model calls and no background refresh. */
const jointState={epoch:0,selected:[],data:null,busy:false,controller:null,jobId:null,pickerRequest:0,history:[],filters:{}};
const jointDraftKey='literature-reviewer.discovery-draft.v1';
const jointExporter=new DiscoveryExport('joint');
function jointDraft(){try{return JSON.parse(localStorage.getItem(jointDraftKey))||{};}catch{return {};}}
function saveJointDraft(){
  if(!$('#joint-question'))return;
  try{localStorage.setItem(jointDraftKey,JSON.stringify({selected:jointState.selected,question:$('#joint-question').value,keywords:$('#joint-keywords').value}));}catch{}
  showJointChanged();
}
function jointParams(){return {itemKeys:jointState.selected.map(i=>i.key).sort(),question:$('#joint-question').value.trim().replace(/\s+/g,' '),keywords:$('#joint-keywords').value.trim().replace(/\s+/g,' ')};}
function showJointChanged(){
  if(!$('#joint-changed'))return;
  const p=jointState.data?.parameters;
  const now=jointParams();
  const changed=p&&(JSON.stringify(p.itemKeys)!==JSON.stringify(now.itemKeys)||p.question!==now.question||p.keywords!==now.keywords);
  $('#joint-changed').textContent=changed?'表单已修改。下方仍是上一次检索结果，点击“查找 / 更新”才会查询新条件。':'';
}
function renderJointSelected(){
  $('#joint-selected').innerHTML=jointState.selected.map(i=>`<li><span>${escapeHtml(i.title)}<small>${escapeHtml(authorSummary(i.creators||[]))} · ${escapeHtml(i.date||'年份未记录')}</small></span><button class="text-button" data-remove="${escapeHtml(i.key)}" aria-label="移除 ${escapeHtml(i.title)}" ${jointState.busy?'disabled':''}>移除</button></li>`).join('');
  $('#joint-count').textContent=`已选 ${jointState.selected.length} / 5 篇`;
  $('#joint-selected').querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{jointState.selected=jointState.selected.filter(i=>i.key!==b.dataset.remove);renderJointSelected();saveJointDraft();loadJointPicker();});
}
async function loadJointPicker(){
  const epoch=jointState.epoch,request=++jointState.pickerRequest;
  try{
    const data=await getJson('/api/discovery/library?q='+encodeURIComponent($('#joint-picker-query').value.trim()));
    if(epoch!==jointState.epoch||request!==jointState.pickerRequest)return;
    $('#joint-picker-info').textContent=`找到 ${data.total} 篇${data.total>200?'，显示前 200 篇；可继续搜索缩小范围':''} · 选 2–5 篇不同的论文`;
    $('#joint-picker-list').innerHTML=data.items.map(i=>`<button type="button" class="joint-pick" data-key="${escapeHtml(i.key)}" ${jointState.busy||jointState.selected.some(s=>s.key===i.key)||jointState.selected.length>=5?'disabled':''}><span>${escapeHtml(i.title)}<small>${escapeHtml(authorSummary(i.creators||[]))} · ${escapeHtml(i.date||'年份未记录')}</small></span><strong>＋</strong></button>`).join('')||'<p>没有匹配的文献，请换一个标题关键词。</p>';
    $('#joint-picker-list').querySelectorAll('[data-key]').forEach(b=>b.onclick=()=>{
      if(jointState.busy||jointState.selected.length>=5)return;
      jointState.selected.push(data.items.find(i=>i.key===b.dataset.key));renderJointSelected();saveJointDraft();loadJointPicker();
    });
  }catch(e){if(epoch===jointState.epoch&&request===jointState.pickerRequest)$('#joint-picker-info').textContent=e.message;}
}
function renderJointHistory(){
  $('#joint-history-list').innerHTML=jointState.history.length?jointState.history.map(g=>`<button class="joint-history-entry" data-group="${escapeHtml(g.id)}"><strong>${escapeHtml(g.parameters.question||g.parameters.keywords||'多篇论文联合查找')}</strong>${g.parameters.question&&g.parameters.keywords?`<small>检索词：${escapeHtml(g.parameters.keywords)}</small>`:''}<span>${escapeHtml(g.seeds.map(s=>s.title).join('；'))}</span><small>${g.count} 篇候选 · ${escapeHtml(discoveryTime(g.searchedAt))}</small></button>`).join(''):'<p>完成检索后，这里会保存最近的 20 组记录。</p>';
  $('#joint-history-list').querySelectorAll('[data-group]').forEach(b=>b.onclick=()=>discoveryNav('#/discover/'+b.dataset.group));
}
async function refreshJointHistory(epoch){try{const h=await getJson('/api/discovery/groups');if(epoch!==jointState.epoch)return;jointState.history=h.groups;renderJointHistory();$('#joint-history-warning').textContent=h.unreadable?`${h.unreadable} 份记录暂时无法读取，原文件已保留。`:'';}catch(e){if(epoch===jointState.epoch)$('#joint-history-warning').textContent=e.message;}}
function jointFilterValues(){return {from:$('#joint-year-from').value,to:$('#joint-year-to').value,review:$('#joint-reviews').checked,oa:$('#joint-oa').checked,onlyNew:$('#joint-new').checked,excluded:$('#joint-show-excluded').checked,kind:$('#joint-kind').value};}
function renderJointResults(){
  const data=jointState.data,all=data?.results||[],f=jointFilterValues();jointState.filters=f;
  const from=f.from?Number(f.from):null,to=f.to?Number(f.to):null;
  const invalid=(from!==null&&(!Number.isInteger(from)||from<1500||from>2200))||(to!==null&&(!Number.isInteger(to)||to<1500||to>2200))||(from!==null&&to!==null&&from>to);
  $('#joint-filter-error').textContent=invalid?'请输入 1500–2200 范围内的年份，起始年份不能晚于结束年份。':'';
  const visible=invalid?[]:all.filter(h=>(!h.excluded||f.excluded)&&(!f.onlyNew||!h.inLibrary)&&(!f.review||h.isReview===true)&&(!f.oa||h.isOpenAccess===true||!!h.oaUrl)&&(!from||h.year>=from)&&(!to||(h.year&&h.year<=to))&&(f.kind==='all'||h.relations.some(r=>r.kind===f.kind)));
  $('#joint-result-count').textContent=`显示 ${visible.length} / ${all.length} 篇候选 · ${all.filter(h=>h.excluded).length} 篇已标记不感兴趣`;
  $('#joint-results').innerHTML=visible.length?visible.map(h=>{
    const coverage=h.relatedSeedKeys?.length||0;
    const extra=`<div class="joint-evidence"><strong>${coverage?`关联到 ${coverage} / ${data.seeds.length} 篇起始论文`:'暂无逐篇关联证据'}</strong>${h.questionTerms?.length?`<p>标题 / 摘要命中：${escapeHtml(h.questionTerms.join(' · '))}</p>`:''}${h.isReview?'<span class="discovery-tag">综述</span>':''}${h.isOpenAccess?'<span class="discovery-tag">开放获取</span>':''}${h.excluded?'<p>已标记不感兴趣</p>':''}<button class="text-button joint-feedback" data-result="${escapeHtml(h.resultId)}" data-excluded="${!h.excluded}">${h.excluded?'恢复这篇文献':'不感兴趣'}</button></div>`;
    return discoveryCard(h).replace('<footer>',extra+'<footer>');
  }).join(''):`<div class="discovery-empty"><span>⌕</span><h3>${all.length?'当前筛选下没有文献':'围绕研究问题继续找文献'}</h3><p>${all.length?'放宽年份或类型筛选，或勾选“显示不感兴趣”。缺少年份、综述或开放获取信息的文献不会通过对应筛选。':'选择 2–5 篇起始论文后点击查找。结果将保存在本电脑，下次可直接打开。'}</p></div>`;
  $('#joint-results').querySelectorAll('.discovery-open-local').forEach(b=>b.onclick=()=>selectItem(b.dataset.key));
  $('#joint-results').querySelectorAll('.joint-feedback').forEach(b=>b.onclick=async()=>{
    if(jointState.busy||!data.saved)return;
    const epoch=jointState.epoch;b.disabled=true;
    try{const result=await postJson(`/api/discovery/groups/${data.id}/feedback`,{resultId:b.dataset.result,excluded:b.dataset.excluded==='true'});if(epoch!==jointState.epoch)return;jointState.data=result;renderJointResults();}
    catch(e){if(epoch===jointState.epoch){$('#joint-status').textContent=e.message;b.disabled=false;}}
  });
  $('#joint-results').querySelectorAll('.joint-feedback').forEach(b=>b.disabled=jointState.busy||!data.saved);
  jointExporter.update({data,visible,resultsElement:$('#joint-results'),scope:{groupId:data?.id||null},busy:jointState.busy});
}
function renderJointData(){
  const data=jointState.data;
  $('#joint-jump-results')?.classList.toggle('hidden',!data);
  $('#joint-active-query').textContent=data?`当前结果：${data.parameters.question||'未指定研究问题'}${data.parameters.keywords?' · 检索词：'+data.parameters.keywords:''} · ${data.seeds.map(s=>s.title).join('；')}`:'尚未开始检索';
  $('#joint-saved').textContent=data?.saved?`已保存在本电脑 · ${discoveryTime(data.searchedAt)} · 再次打开不会重新检索`:'查找完成后自动保存，不消耗模型 Token';
  $('#joint-query-plan').textContent=data?.plan?.query?`实际检索词：${data.plan.query}${data.plan.expandedTerms.length?' · 从本电脑词表展开：'+data.plan.expandedTerms.join('、'):''}${data.plan.notice?' · '+data.plan.notice:''}`:'';
  $('#joint-notice').textContent=[data?.stale?'部分起始论文或检索条件已变化，或沿用了旧的单篇结果；点击“查找 / 更新”才会刷新。':'',data?.preserved?'本次刷新未取得可用的新数据，保留上次结果。':''].filter(Boolean).join(' ');
  const providers=(data?.latestAttempt||data)?.providers||[];
  $('#joint-providers').innerHTML=providers.map(p=>`<section class="discovery-provider"><div><strong>${escapeHtml(p.source)} · ${escapeHtml(p.task)}</strong><span>${p.cached?'已存结果':p.completed?'已完成查询':'未完成查询'}</span></div>${p.seedTitle?`<p>${escapeHtml(p.seedTitle)}</p>`:''}${(p.warnings||[]).map(w=>`<p class="discovery-warning">${escapeHtml(w)}</p>`).join('')}${p.seedKey&&!p.match?`<button class="text-button joint-confirm-seed" data-key="${escapeHtml(p.seedKey)}">打开该论文，核对起始匹配 →</button>`:''}</section>`).join('');
  $('#joint-providers').querySelectorAll('[data-key]').forEach(b=>b.onclick=()=>window.discoveryWorkspace.open(b.dataset.key));
  showJointChanged();renderJointResults();
}
function stopJoint(){
  jointState.controller?.abort();
  if(jointState.jobId)fetch(`/api/generations/${jointState.jobId}/cancel`,{method:'POST',keepalive:true}).catch(()=>{});
}
function jointBusy(value){
  jointState.busy=value;
  $('#joint-form-fields').disabled=value;$('#joint-run').disabled=value;
  $('#joint-stop').classList.toggle('hidden',!value);$('#joint-save-settings').disabled=value;
  renderJointSelected();loadJointPicker();renderJointResults();
}
async function runJoint(){
  if(jointState.busy)return;
  const params=jointParams(),epoch=jointState.epoch;
  if(params.itemKeys.length<2||params.itemKeys.length>5){$('#joint-status').textContent='请先选择 2–5 篇不同的起始论文。';return;}
  const same=jointState.data?.saved&&JSON.stringify(jointState.data.parameters)===JSON.stringify(params);
  if(same&&!confirm('重新联网更新这组检索？不调用模型，但会使用学术数据服务额度。'))return;
  saveJointDraft();jointBusy(true);jointState.controller=new AbortController();jointState.jobId=crypto.randomUUID().replaceAll('-','');
  $('#joint-status').textContent='正在查询起始论文、研究问题和联合推荐。可随时停止；离开页面也会发送停止请求。';
  try{
    const data=await postJson('/api/discovery/groups',{...params,force:!!same},{signal:jointState.controller.signal,headers:{'X-Generation-ID':jointState.jobId}});
    if(epoch!==jointState.epoch)return;
    if(data.cancelled){$('#joint-status').textContent='检索已停止，已有结果保留。';return;}
    jointState.data=data;
    if(data.saved)history.replaceState(null,'','#/discover/'+data.id);
    $('#joint-picker').open=false;
    renderJointData();refreshJointHistory(epoch);
    $('#joint-status').textContent=data.preserved?'已保留上次结果，请查看数据源状态。':data.saved?`已保存 ${data.results.length} 篇候选。可继续筛选或标记不感兴趣。`:'尚未取得可保存的结果，请查看数据源状态。';
  }catch(e){if(epoch===jointState.epoch)$('#joint-status').textContent=e.name==='AbortError'?'已停止等待，并发送停止请求；已有结果保留。':e.message;}
  finally{if(epoch===jointState.epoch){jointState.controller=null;jointState.jobId=null;jointBusy(false);}}
}
async function saveJointSettings(){
  const epoch=jointState.epoch,b=$('#joint-save-settings');b.disabled=true;
  try{
    const c=await postJson('/api/discovery/settings',{openalexKey:$('#joint-oa-key').value,semanticScholarKey:$('#joint-s2-key').value,clearOpenalexKey:$('#joint-clear-oa').checked,clearSemanticScholarKey:$('#joint-clear-s2').checked});
    if(epoch!==jointState.epoch)return;
    $('#joint-oa-key').value='';$('#joint-s2-key').value='';$('#joint-clear-oa').checked=false;$('#joint-clear-s2').checked=false;showJointSettings(c);
    $('#joint-settings-message').textContent='已保存。点击查找才会联网。';
  }catch(e){if(epoch===jointState.epoch)$('#joint-settings-message').textContent=e.message;}
  finally{if(epoch===jointState.epoch)b.disabled=false;}
}
function showJointSettings(c){$('#joint-config').textContent=`OpenAlex：${c.openalexConfigured?'已保存 Key':'未配置 Key'} · Semantic Scholar：${c.semanticScholarConfigured?'已保存 Key':'未配置 Key'}`;}
async function jointRoute(id,seedKey){
  const epoch=++jointState.epoch;Object.assign(jointState,{busy:false,data:null,selected:[],filters:{}});
  document.title='联合查找文献 · 文献梳理工具';window.scrollTo(0,0);
  const panel=$('#joint-workspace');
  panel.innerHTML='<button class="back-button joint-back">← 返回文献库</button><p class="analysis-loading">正在读取本电脑的检索记录…</p>';
  panel.querySelector('.joint-back').onclick=()=>discoveryNav('#/library');
  try{
    const [data,config]=await Promise.all([id?getJson('/api/discovery/groups/'+id):Promise.resolve(null),getJson('/api/discovery/settings')]);
    if(epoch!==jointState.epoch)return;
    const draft=data?{selected:data.seeds,...data.parameters}:jointDraft();
    jointState.selected=Array.isArray(draft.selected)?draft.selected.filter(i=>i&&/^[A-Z0-9]+$/.test(i.key)).slice(0,5):[];
    if(seedKey&&!jointState.selected.some(s=>s.key===seedKey)){
      const seed=await getJson('/api/items/'+seedKey);if(epoch!==jointState.epoch)return;
      if(jointState.selected.length>=5)jointState.selected.pop();jointState.selected.push(seed);
    }
    jointState.data=data;
    panel.innerHTML=`<button class="back-button joint-back">← 返回文献库</button><header class="discovery-heading"><div><div class="eyebrow">EXPLORE A RESEARCH QUESTION</div><h2 tabindex="-1">联合查找文献</h2><p>用几篇已读论文，围绕一个具体问题，寻找下一步要读的研究。</p></div><button id="joint-new-search" class="secondary-button">新建检索</button></header><div class="joint-top-grid"><section class="joint-form"><fieldset id="joint-form-fields"><legend>1 · 选择 2–5 篇起始论文</legend><span id="joint-count"></span><ul id="joint-selected" class="joint-selected"></ul><details id="joint-picker" open><summary>从文献库添加论文</summary><label for="joint-picker-query">搜索标题或摘要</label><input id="joint-picker-query" type="search" placeholder="输入标题关键词"/><p id="joint-picker-info" role="status"></p><div id="joint-picker-list"></div></details><label for="joint-question" class="joint-label">2 · 你想研究什么问题？</label><textarea id="joint-question" rows="3" maxlength="1000" placeholder="例如：日冕仪中，哪些波前控制方法能改善宽波段对比度？">${escapeHtml(draft.question||'')}</textarea><label for="joint-keywords">英文检索词（可选）</label><input id="joint-keywords" maxlength="300" placeholder="例如 coronagraph broadband wavefront control" value="${escapeHtml(draft.keywords||'')}"/><p class="joint-hint">英文检索词优先使用；中文问题会参考你的专业词表和研究方向中的同义词。问题查询与多篇关联结果合并，不调用大模型。</p></fieldset><div class="joint-actions"><button id="joint-run" class="primary-button">查找 / 更新</button><button id="joint-stop" class="text-button hidden">停止检索</button></div><p id="joint-status" class="discovery-status" role="status"></p><p id="joint-changed" class="discovery-warning" role="status"></p></section><aside class="joint-history"><h3>已保存检索</h3><p>直接打开已有结果，不会重新联网。</p><div id="joint-history-list"></div><p id="joint-history-warning" role="status"></p></aside></div><section class="joint-results-section"><h3>候选文献</h3><p id="joint-active-query"></p><p id="joint-saved"></p><p id="joint-query-plan"></p><p id="joint-notice" class="discovery-warning" role="status"></p><p class="joint-hint">按问题检索命中、标题 / 摘要词语命中、关联起始论文数量及数据源排名排序。联合推荐不代表与每篇论文均有独立关联；这里展示的是待核对候选。</p><div class="joint-filters"><label>起始年份<input id="joint-year-from" type="number" min="1500" max="2200" placeholder="不限"/></label><label>结束年份<input id="joint-year-to" type="number" min="1500" max="2200" placeholder="不限"/></label><label>关联类型<select id="joint-kind"><option value="all">全部</option><option value="question">围绕研究问题</option><option value="similar">相似研究</option><option value="reference">前置文献</option><option value="citing">后续研究</option></select></label><label><input id="joint-reviews" type="checkbox"/> 仅综述</label><label><input id="joint-oa" type="checkbox"/> 仅开放获取</label><label><input id="joint-new" type="checkbox"/> 隐藏库内已有</label><label><input id="joint-show-excluded" type="checkbox"/> 显示不感兴趣</label><button id="joint-clear-filters" class="text-button">重置筛选</button></div><p class="joint-hint">筛选只作用于已取回的最多 60 篇候选；缺少对应信息的文献无法通过该项筛选。标记“不感兴趣”仅影响本组显示，可随时恢复。</p><p id="joint-filter-error" class="discovery-warning" role="status"></p><p id="joint-result-count" role="status"></p><div id="joint-results" class="discovery-results"></div></section><section class="discovery-source-section"><details><summary>检索来源与匹配情况</summary><div id="joint-providers"></div></details><details class="discovery-settings"><summary>检索服务设置</summary><p id="joint-config"></p><p>向学术服务发送所选论文的标题、摘要、DOI 和研究问题，不上传 PDF。检索 Key 与模型 Key 分开；无 Key 时可能限流。${discoveryLink('https://openalex.org/settings/api','获取 OpenAlex Key ↗')} · ${discoveryLink('https://www.semanticscholar.org/product/api','申请 Semantic Scholar Key ↗')}</p><div class="discovery-key-grid"><label>OpenAlex API Key<input id="joint-oa-key" type="password" autocomplete="new-password" placeholder="留空保留已存 Key"/><span><input id="joint-clear-oa" type="checkbox"/> 清除已存 Key</span></label><label>Semantic Scholar API Key<input id="joint-s2-key" type="password" autocomplete="new-password" placeholder="留空保留已存 Key"/><span><input id="joint-clear-s2" type="checkbox"/> 清除已存 Key</span></label></div><button id="joint-save-settings" class="secondary-button">保存检索设置</button><p id="joint-settings-message" role="status"></p></details></section>`;
    panel.querySelector('.joint-back').onclick=()=>discoveryNav('#/library');
    const newButton=$('#joint-new-search'),headingActions=document.createElement('div');
    headingActions.className='joint-heading-actions';newButton.before(headingActions);headingActions.append(newButton);
    $('#joint-new-search').insertAdjacentHTML('afterend','<button id="joint-jump-results" class="text-button">查看候选结果 ↓</button>');
    $('#joint-jump-results').onclick=()=>$('.joint-results-section').scrollIntoView({behavior:'smooth',block:'start'});
    $('#joint-picker').open=jointState.selected.length<2;
    $('#joint-new-search').onclick=()=>{try{localStorage.removeItem(jointDraftKey);}catch{}discoveryNav('#/discover');};
    let timer;$('#joint-picker-query').oninput=()=>{clearTimeout(timer);jointState.pickerRequest++;timer=setTimeout(()=>{if(epoch===jointState.epoch)loadJointPicker();},250);};
    for(const id of ['joint-question','joint-keywords'])$('#'+id).oninput=saveJointDraft;
    $('#joint-run').onclick=runJoint;$('#joint-stop').onclick=stopJoint;$('#joint-save-settings').onclick=saveJointSettings;
    panel.querySelectorAll('.joint-filters input,.joint-filters select').forEach(el=>el.onchange=renderJointResults);
    $('#joint-clear-filters').onclick=()=>{panel.querySelectorAll('.joint-filters input').forEach(i=>{i.type==='checkbox'?i.checked=false:i.value='';});$('#joint-kind').value='all';renderJointResults();};
    renderJointSelected();renderJointData();showJointSettings(config);loadJointPicker();refreshJointHistory(epoch);saveJointDraft();panel.querySelector('h2').focus({preventScroll:true});
  }catch(e){if(epoch===jointState.epoch){panel.querySelector('.analysis-loading')?.remove();panel.insertAdjacentHTML('beforeend',`<p class="discovery-notice" role="alert">${escapeHtml(e.message)}</p>`);}}
}
window.jointDiscovery={route:jointRoute,leave(){jointState.epoch++;stopJoint();jointState.jobId=null;jointState.controller=null;jointState.busy=false;jointState.pickerRequest++;jointExporter.reset();}};
$('#nav-discover').onclick=()=>discoveryNav('#/discover');
window.addEventListener('pagehide',stopJoint);
