/* Term lessons reuse the evidence-linked chapter reader and its free cache UI. */
async function openTermReading(item, term = '') {
  term = String(term || '').replace(/\s+/g, ' ').trim();
  if (term.length > 150) return;
  dismissSelectionTranslation();
  openAnalysis('术语精讲', 'DEEP READING');
  $('#analysis-modal-eyebrow').textContent = 'CONCEPT LEARNING';
  const key = `term:${item.key}`;
  let view = deepViews.get(key);
  if (!view) {
    view = {item,kind:'term',section:'',archive:-1,revision:-1,pending:null,error:'',data:null,request:0};
    deepViews.set(key,view);
  }
  view.item=item;activeDeepView=view;
  if(view.pending && view.data) {
    const match=view.data.chapters.find(c=>c.term.toLowerCase()===term.toLowerCase());
    if(match){view.section=match.id;view.archive=-1;view.revision=-1;}
    paintDeepReading(view);return;
  }
  view.error='';
  if(view.data) paintDeepReading(view);
  const request=++view.request;
  try {
    const data=await getJson(`/api/items/${item.key}/term-reading${term ? `?term=${encodeURIComponent(term)}` : ''}`);
    if(request!==view.request)return;
    view.data=data;
    const match=data.chapters.find(c=>c.term.toLowerCase()===term.toLowerCase());
    if(match){view.section=match.id;view.archive=-1;view.revision=-1;}
    else if(!data.chapters.some(c=>c.id===view.section)) view.section=Object.keys(data.reading?.drafts || {})[0] || Object.keys(data.reading?.sections || {})[0] || data.chapters[0]?.id || '';
    paintDeepReading(view);
  } catch(error) {
    if(request!==view.request)return;
    view.error=error.message;
    if(view.data) paintDeepReading(view);
    else if(activeDeepView===view) $('#analysis-modal-body').innerHTML=`<p class="analysis-error">${escapeHtml(error.message)}</p>`;
  }
}
