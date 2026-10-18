/* Literature discovery: metadata APIs only, never model generation. */
const discoveryState={epoch:0,key:null,item:null,data:null,busy:false,filter:'all',onlyNew:false,controller:null};
const discoveryKinds={similar:'相似研究',reference:'前置文献',citing:'后续研究'};
const discoveryExporter=new DiscoveryExport('discovery');
function discoveryUrl(value){try{const url=new URL(value);return ['https:','http:'].includes(url.protocol)&&!url.username&&!url.password?url.href:'';}catch{return '';}}
function discoveryLink(url,label,className='text-button'){
  const safe=discoveryUrl(url);return safe?`<a href="${escapeHtml(safe)}" class="${className}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)}</a>`:'';
}
function discoveryTime(value){return value?new Date(value).toLocaleString('zh-CN',{hour12:false}):'';}
function discoveryNav(hash){history.pushState(null,'',hash);applyRoute();}
function discoveryCard(hit){
  const kinds=[...new Set(hit.relations.map(r=>r.kind))];
  const authors=authorSummary(hit.creators || []);
  const evidence=r=>`<li><strong>${escapeHtml(r.source)}</strong> · ${escapeHtml(r.text)}${r.seedKey?`<span class="joint-seed-name">关联起点：${escapeHtml(r.seedTitle)}</span>`:''}</li>`;
  const reasons=`<ul class="discovery-reasons">${hit.relations.slice(0,3).map(evidence).join('')}</ul>${hit.relations.length>3?`<details class="discovery-abstract"><summary>展开其余 ${hit.relations.length-3} 条关联依据</summary><ul class="discovery-reasons">${hit.relations.slice(3).map(evidence).join('')}</ul></details>`:''}`;
  return `<article class="discovery-card"><div class="discovery-card-top"><div class="discovery-tags">${kinds.map(k=>`<span class="discovery-tag ${escapeHtml(k)}">${escapeHtml(discoveryKinds[k]||(k==='question'?'围绕研究问题':k))}</span>`).join('')}${hit.inLibrary?'<span class="discovery-tag library">已在文献库</span>':''}</div><span class="discovery-year">${escapeHtml(hit.year || '年份未记录')}</span></div><h3>${escapeHtml(hit.title)}</h3><p class="discovery-authors">${escapeHtml(authors)}</p><p class="discovery-venue">${escapeHtml(hit.publicationTitle || '来源未记录')}</p>${reasons}${hit.abstract?`<details class="discovery-abstract"><summary>查看摘要</summary><p>${escapeHtml(hit.abstract)}</p></details>`:'<p class="discovery-no-abstract">数据源未提供摘要，需打开原文进一步判断。</p>'}<footer>${discoveryLink(hit.url,hit.doi?'DOI / 原文 ↗':'数据源页面 ↗','secondary-button')}${hit.oaUrl&&hit.oaUrl!==hit.url?discoveryLink(hit.oaUrl,'开放获取 ↗'):''}${hit.inLibrary?`<button class="text-button discovery-open-local" data-key="${escapeHtml(hit.libraryKey)}">打开库内文献 →</button>`:''}<small>${escapeHtml(hit.sources.join(' · '))}</small></footer></article>`;
}
function renderDiscoveryResults(){
  const data=discoveryState.data || {}, results=data.results || [];
  const visible=results.filter(hit=>(discoveryState.filter==='all'||hit.relations.some(r=>r.kind===discoveryState.filter))&&(!discoveryState.onlyNew||!hit.inLibrary));
  $('#discovery-filters').innerHTML=`<div class="discovery-tabs" role="group" aria-label="关联类型"><button data-kind="all" aria-pressed="${discoveryState.filter==='all'}">全部 <span>${results.length}</span></button>${Object.entries(discoveryKinds).map(([kind,label])=>`<button data-kind="${kind}" aria-pressed="${discoveryState.filter===kind}">${label} <span>${results.filter(h=>h.relations.some(r=>r.kind===kind)).length}</span></button>`).join('')}</div><label class="discovery-new-filter"><input id="discovery-only-new" type="checkbox" ${discoveryState.onlyNew?'checked':''}/> 隐藏库内已有文献</label>`;
  $('#discovery-filters').querySelectorAll('[data-kind]').forEach(button=>button.onclick=()=>{discoveryState.filter=button.dataset.kind;renderDiscoveryResults();});
  $('#discovery-only-new').onchange=event=>{discoveryState.onlyNew=event.target.checked;renderDiscoveryResults();};
  $('#discovery-results').innerHTML=visible.length?visible.map(discoveryCard).join(''):`<div class="discovery-empty"><span>⌕</span><h3>${results.length?'当前筛选下没有文献':data.saved?'本次未找到可展示的相关文献':'从这篇论文继续探索'}</h3><p>${results.length?'可以切换关联类型，或显示库内已有文献。':data.saved?'可以检查下方数据源状态、补充检索 Key，或稍后主动刷新。':'点击“开始查找”，查找相似研究、它引用的前置文献，以及引用它的后续工作。'}</p></div>`;
  $('#discovery-results').querySelectorAll('.discovery-open-local').forEach(button=>button.onclick=()=>selectItem(button.dataset.key));
  discoveryExporter.update({data,visible,resultsElement:$('#discovery-results'),scope:{itemKey:discoveryState.key},busy:discoveryState.busy});
}
function renderDiscoveryData(){
  const data=discoveryState.data || {},attempt=data.latestAttempt || data;
  $('#discovery-run').textContent=data.saved?'刷新检索':'开始查找';
  $('#discovery-saved').textContent=data.saved?`结果保存在本电脑 · ${discoveryTime(data.searchedAt)} · 打开已有结果不联网检索`:'尚未保存检索结果';
  const notice=[];
  if(data.stale)notice.push('起始论文的元数据已变化，当前显示旧检索结果；点击刷新才按新资料查询。');
  if(data.preserved)notice.push('本次更新未取得可用结果，已保留之前保存的结果。');
  $('#discovery-notice').textContent=notice.join(' ');$('#discovery-notice').classList.toggle('hidden',!notice.length);
  $('#discovery-providers').innerHTML=(attempt.providers || []).map(p=>`<section class="discovery-provider"><div><strong>${escapeHtml(p.source)}</strong><span>${p.match?`已匹配 · ${p.completed}/3 项查询完成`:'尚未匹配'}</span></div>${p.match?`<p class="discovery-match">起始论文：${escapeHtml(p.match.title)}${p.match.year?' · '+escapeHtml(p.match.year):''}</p>`:''}${p.warnings.map(w=>`<p class="discovery-warning">${escapeHtml(w)}</p>`).join('')}</section>`).join('');
  const candidates=attempt.candidates || data.candidates || [];
  $('#discovery-candidates').innerHTML=candidates.length?`<details class="discovery-candidate-list" ${!(data.results || []).length?'open':''}><summary>核对起始论文候选（${candidates.length}）</summary><p>以下是可能对应你导入文献的记录，并非相关推荐。核对标题、作者和年份后再确认。本次将只使用你确认的数据源。</p>${candidates.map((c,i)=>`<article><div><strong>${escapeHtml(c.title)}</strong><p>${escapeHtml(authorSummary(c.creators))} · ${escapeHtml(c.year || '年份未记录')}</p><small>${escapeHtml(c.source)}${c.doi?' · '+escapeHtml(c.doi):''}</small></div><button class="secondary-button discovery-confirm-match" data-index="${i}">确认是这篇</button></article>`).join('')}</details>`:'';
  $('#discovery-candidates').querySelectorAll('button').forEach(button=>button.onclick=()=>{
    const candidate=candidates[Number(button.dataset.index)];
    if(confirm(`确认以这篇论文作为检索起点？\n\n${candidate.title}\n${candidate.year || ''} · ${candidate.source}`))runDiscovery({source:candidate.source,id:candidate.sourceId});
  });
  renderDiscoveryResults();
}
async function runDiscovery(selection=null){
  if(discoveryState.busy)return;
  const {key,epoch}=discoveryState,hadSaved=discoveryState.data?.saved;
  if(hadSaved&&!selection&&!confirm('重新联网查询并更新这篇文献的相关结果？不调用模型，但会使用检索服务额度；查询失败会保留已有结果。'))return;
  discoveryState.busy=true;discoveryState.controller=new AbortController();discoveryState.jobId=crypto.randomUUID().replaceAll('-','');
  renderDiscoveryResults();
  $('#discovery-stop').classList.remove('hidden');
  $('#discovery-run').disabled=true;$('#discovery-save-settings').disabled=true;
  $('#discovery-candidates').querySelectorAll('button').forEach(b=>b.disabled=true);
  $('#discovery-status').textContent='正在匹配论文并查询两个数据源，请稍候。服务超时或限流时会保留可用结果。';
  $('#discovery-status').classList.remove('failed');
  try{
    const result=await postJson(`/api/items/${key}/discovery`,{force:!!hadSaved||!!selection,...(selection?{selection}:{})},{signal:discoveryState.controller.signal,headers:{'X-Generation-ID':discoveryState.jobId}});
    if(epoch!==discoveryState.epoch)return;
    if(result.cancelled){$('#discovery-status').textContent='检索已停止，已存结果保留。';return;}
    discoveryState.data=result;renderDiscoveryData();
    $('#discovery-status').textContent=result.preserved?'刷新未取得新结果，已保留旧结果。':result.saved?`已保存 ${result.results.length} 篇候选文献。推荐依据来自检索数据，并非全文评价。`:'尚未取得结果，请查看数据源提示或核对起始论文候选。';
  }catch(error){
    if(epoch!==discoveryState.epoch)return;
    $('#discovery-status').textContent=error.name==='AbortError'?'已停止等待检索，已发送停止请求。':error.message;$('#discovery-status').classList.toggle('failed',error.name!=='AbortError');
  }finally{
    if(epoch===discoveryState.epoch){discoveryState.busy=false;discoveryState.controller=null;discoveryState.jobId=null;$('#discovery-stop').classList.add('hidden');$('#discovery-run').disabled=false;$('#discovery-save-settings').disabled=false;$('#discovery-candidates').querySelectorAll('button').forEach(b=>b.disabled=false);renderDiscoveryResults();}
  }
}
function stopDiscovery(){
  const id=discoveryState.jobId;
  discoveryState.controller?.abort();
  if(id)fetch(`/api/generations/${id}/cancel`,{method:'POST',keepalive:true}).catch(()=>{});
}
async function saveDiscoverySettings(){
  const epoch=discoveryState.epoch,button=$('#discovery-save-settings');button.disabled=true;
  try{
    const config=await postJson('/api/discovery/settings',{openalexKey:$('#discovery-oa-key').value,semanticScholarKey:$('#discovery-s2-key').value,clearOpenalexKey:$('#discovery-clear-oa').checked,clearSemanticScholarKey:$('#discovery-clear-s2').checked});
    if(epoch!==discoveryState.epoch)return;
    $('#discovery-oa-key').value='';$('#discovery-s2-key').value='';$('#discovery-clear-oa').checked=false;$('#discovery-clear-s2').checked=false;
    showDiscoveryConfig(config);$('#discovery-settings-message').textContent='配置已保存在本电脑。点击开始查找或刷新才会联网。';
  }catch(error){if(epoch===discoveryState.epoch)$('#discovery-settings-message').textContent=error.message;}
  finally{if(epoch===discoveryState.epoch)button.disabled=false;}
}
function showDiscoveryConfig(config){
  $('#discovery-config-state').textContent=`OpenAlex：${config.openalexConfigured?'已保存 Key':'未配置 Key'} · Semantic Scholar：${config.semanticScholarConfigured?'已保存 Key':'未配置 Key'}`;
}
async function discoveryRoute(key){
  const epoch=++discoveryState.epoch;Object.assign(discoveryState,{key,item:null,data:null,busy:false,filter:'all',onlyNew:false});
  document.title='发现相关文献 · 文献梳理工具';window.scrollTo(0,0);
  const panel=$('#discovery-workspace');
  panel.innerHTML='<button id="discovery-back" class="back-button">← 返回起始论文</button><p class="analysis-loading" role="status">正在读取已保存结果…</p>';
  $('#discovery-back').onclick=()=>discoveryNav(`#/items/${key}`);
  try{
    const [item,data,config]=await Promise.all([getJson(`/api/items/${key}`),getJson(`/api/items/${key}/discovery`),getJson('/api/discovery/settings')]);
    if(epoch!==discoveryState.epoch)return;
    discoveryState.item=item;discoveryState.data=data;
    panel.innerHTML=`<button id="discovery-back" class="back-button">← 返回起始论文</button><header class="discovery-heading"><div><div class="eyebrow">FOLLOW THE RESEARCH</div><h2 tabindex="-1">发现相关文献</h2><p>沿着问题、方法与引用，找到下一篇值得读的论文。</p></div><a class="text-button" href="#discovery-settings">检索设置 ↓</a></header><section class="discovery-seed"><span class="discovery-seed-label">起始论文</span><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(authorSummary(item.creators))}${item.date?' · '+escapeHtml(item.date):''}</p>${item.doi?`<small>DOI · ${escapeHtml(item.doi)}</small>`:''}</section><section class="discovery-run-row"><div><p id="discovery-saved"></p><small>按数据源顺序与多源命中综合排列，兼顾三类关系。引用关系不等于质量评价。</small></div><button id="discovery-run" class="primary-button">开始查找</button></section><p id="discovery-status" class="discovery-status" role="status"></p><p id="discovery-notice" class="discovery-notice hidden" role="status"></p><div id="discovery-filters" class="discovery-filters"></div><div id="discovery-results" class="discovery-results"></div><section class="discovery-source-section"><h3>检索来源与匹配情况</h3><p>默认只向学术数据服务发送 DOI、标题和摘要，不上传 PDF，不调用你配置的大模型。这里只展示部分相关结果，不是完整的系统综述检索。</p><div id="discovery-providers"></div><div id="discovery-candidates"></div><details id="discovery-settings" class="discovery-settings"><summary>检索服务设置</summary><p id="discovery-config-state"></p><p>可先尝试无 Key 查询；如果提示鉴权、限流或额度不足，请填写对应服务的 Key。它们与模型 API Key 不同，服务可用性与额度由提供方决定。</p><div class="discovery-key-grid"><label>OpenAlex API Key<input id="discovery-oa-key" type="password" autocomplete="new-password" placeholder="留空保留已存 Key"/>${discoveryLink('https://openalex.org/settings/api','获取 OpenAlex Key ↗')}<span><input id="discovery-clear-oa" type="checkbox"/> 清除已存 OpenAlex Key</span></label><label>Semantic Scholar API Key<input id="discovery-s2-key" type="password" autocomplete="new-password" placeholder="留空保留已存 Key"/>${discoveryLink('https://www.semanticscholar.org/product/api','查看 API Key 申请说明 ↗')}<span><input id="discovery-clear-s2" type="checkbox"/> 清除已存 Semantic Scholar Key</span></label></div><button id="discovery-save-settings" class="secondary-button">保存检索设置</button><p id="discovery-settings-message" role="status"></p></details></section>`;
    $('#discovery-back').onclick=()=>discoveryNav(`#/items/${key}`);
    $('.discovery-heading').insertAdjacentHTML('afterend','<button id="discovery-use-joint" class="secondary-button">用这篇论文联合查找 →</button>');
    $('#discovery-use-joint').onclick=()=>discoveryNav(`#/discover?seed=${key}`);
    // Keep in-page settings navigation from replacing the application's hash route.
    $('.discovery-heading a').onclick=event=>{event.preventDefault();$('#discovery-settings').open=true;$('#discovery-settings').scrollIntoView({behavior:'smooth',block:'start'});};
    $('#discovery-run').onclick=()=>runDiscovery();$('#discovery-save-settings').onclick=saveDiscoverySettings;
    $('#discovery-run').insertAdjacentHTML('afterend','<button id="discovery-stop" class="text-button hidden">停止检索</button>');
    $('#discovery-stop').onclick=stopDiscovery;
    renderDiscoveryData();showDiscoveryConfig(config);panel.querySelector('h2').focus({preventScroll:true});
  }catch(error){if(epoch!==discoveryState.epoch)return;panel.insertAdjacentHTML('beforeend',`<p class="discovery-notice">${escapeHtml(error.message)}</p>`);panel.querySelector('.analysis-loading')?.remove();}
}
window.discoveryWorkspace={
  open(key){discoveryNav(`#/items/${encodeURIComponent(key)}/discover`);},
  route:discoveryRoute,
  leave(){discoveryState.epoch++;stopDiscovery();discoveryState.jobId=null;discoveryState.controller=null;discoveryState.busy=false;discoveryExporter.reset();}
};
window.addEventListener('pagehide',stopDiscovery);
