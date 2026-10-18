/* Checkbox selection and cached downloads shared by both discovery workspaces. */
class DiscoveryExport {
  constructor(prefix){this.prefix=prefix;this.selected=new Set();this.scope=null;this.downloading=false;this.epoch=0;}
  reset(){this.epoch++;this.selected.clear();this.scope=null;this.downloading=false;}
  update({data,visible,resultsElement,scope,busy=false}){
    const identity=JSON.stringify(scope);
    if(identity!==this.scope){this.reset();this.scope=identity;}
    this.data=data;this.visible=visible;this.scopeValue=scope;this.busy=busy;
    const valid=new Set((data?.results||[]).filter(h=>!h.excluded).map(h=>h.resultId));
    this.selected=new Set([...this.selected].filter(id=>valid.has(id)));
    const id=this.prefix+'-export';
    let toolbar=document.getElementById(id);
    if(!toolbar){
      toolbar=document.createElement('section');toolbar.id=id;toolbar.className='discovery-export';toolbar.setAttribute('aria-label','挑选与导出文献');
      toolbar.innerHTML=`<div class="discovery-export-head"><strong>挑选后导出</strong><span class="export-count" role="status"></span></div><div class="discovery-export-actions"><button type="button" class="text-button export-visible">勾选当前显示</button><button type="button" class="text-button export-clear">清空勾选</button><label>格式<select class="export-format"><option value="ris">RIS · 导入 Zotero</option><option value="bibtex">BibTeX · 论文引用</option><option value="markdown">Markdown · 阅读清单</option></select></label><button type="button" class="secondary-button export-download">下载已选文献</button></div><p class="export-hint">勾选跨筛选保留；下载包含已勾选但被筛选隐藏的文献。离开页面后清空勾选。“不感兴趣”不参与导出。</p><p class="export-message" role="status"></p>`;
      resultsElement.before(toolbar);
      toolbar.querySelector('.export-visible').onclick=()=>{for(const h of this.visible)if(!h.excluded)this.selected.add(h.resultId);this.syncChecks();this.refresh();};
      toolbar.querySelector('.export-clear').onclick=()=>{this.selected.clear();this.syncChecks();this.refresh();};
      toolbar.querySelector('.export-download').onclick=()=>this.download();
    }
    this.toolbar=toolbar;this.resultsElement=resultsElement;
    toolbar.classList.toggle('hidden',!(data?.results?.length));
    const cards=resultsElement.querySelectorAll('.discovery-card');
    cards.forEach((card,index)=>{
      const hit=visible[index];if(!hit?.resultId)return;
      const label=document.createElement('label');label.className='discovery-export-check';
      const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.dataset.result=hit.resultId;checkbox.checked=this.selected.has(hit.resultId);
      checkbox.disabled=busy||this.downloading||!data?.saved||!!hit.excluded;checkbox.setAttribute('aria-label','选择导出：'+hit.title);
      checkbox.onchange=()=>{checkbox.checked?this.selected.add(hit.resultId):this.selected.delete(hit.resultId);this.refresh();};
      label.append(checkbox,document.createTextNode(hit.excluded?'不感兴趣 · 恢复后可导出':'选入导出清单'));card.prepend(label);
    });
    this.refresh();
  }
  syncChecks(){this.resultsElement.querySelectorAll('.discovery-export-check input').forEach(c=>{c.checked=this.selected.has(c.dataset.result);});}
  refresh(){
    const shown=new Set(this.visible.map(h=>h.resultId)),hidden=[...this.selected].filter(id=>!shown.has(id)).length;
    this.toolbar.querySelector('.export-count').textContent=`已选 ${this.selected.size} 篇${hidden?' · 其中 '+hidden+' 篇被筛选隐藏':''}`;
    const disabled=this.busy||this.downloading||!this.data?.saved;
    this.toolbar.querySelector('.export-visible').disabled=disabled||!this.visible.some(h=>!h.excluded);
    this.toolbar.querySelector('.export-clear').disabled=disabled||!this.selected.size;
    this.toolbar.querySelector('.export-format').disabled=disabled;
    this.toolbar.querySelector('.export-download').disabled=disabled||!this.selected.size;
    this.resultsElement.querySelectorAll('.discovery-export-check input').forEach(c=>{const h=this.visible.find(h=>h.resultId===c.dataset.result);c.disabled=disabled||!!h?.excluded;});
  }
  async download(){
    if(this.busy||this.downloading||!this.data?.saved||!this.selected.size)return;
    const epoch=this.epoch,format=this.toolbar.querySelector('.export-format').value,count=this.selected.size;
    const resultIds=[...this.selected];this.downloading=true;this.refresh();
    const message=this.toolbar.querySelector('.export-message');message.textContent='正在整理已保存的元数据…';
    try{
      const data=await postJson('/api/discovery/export',{...this.scopeValue,format,resultIds});
      if(epoch!==this.epoch)return;
      const blob=new Blob([data.content],{type:data.mimeType}),objectUrl=URL.createObjectURL(blob);
      const a=document.createElement('a');a.href=objectUrl;a.download=data.filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(objectUrl),30000);
      message.textContent=`已生成 ${data.count} 篇文献的下载文件。${format==='ris'?'在 Zotero 中选择“文件 → 导入”，选取下载的 .ris 文件。记录按通用类型导出，文献类型和缺失信息可在导入后核对补充。':format==='bibtex'?'可用于 BibTeX / BibLaTeX；记录按通用类型导出，缺失信息需核对原文补充。':'包含原文链接、关联依据及阅读笔记模板。'}${data.count!==count?' 部分选择已变化，请核对下载数量。':''}`;
    }catch(e){if(epoch===this.epoch)message.textContent=e.message;}
    finally{if(epoch===this.epoch){this.downloading=false;this.refresh();}}
  }
}
window.DiscoveryExport=DiscoveryExport;
