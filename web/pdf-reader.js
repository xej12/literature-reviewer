/* Original PDF rendering and selectable text, powered by local Mozilla PDF.js. */
window.selectionPdfView = null;
let pdfJsModule;
document.body.insertAdjacentHTML('beforeend', `<section id="selection-pdf-reader" hidden role="dialog" aria-modal="true" aria-labelledby="selection-pdf-title">
  <header class="selection-pdf-head"><div><small>PDF · 划词阅读</small><h2 id="selection-pdf-title"></h2></div><button id="selection-pdf-close" class="close-button" aria-label="关闭 PDF 阅读器">×</button></header>
  <div class="selection-pdf-toolbar"><label>第 <input id="selection-pdf-number" type="number" min="1" value="1" aria-label="PDF 页码" /> / <span id="selection-pdf-count">…</span> 页</label><button id="selection-pdf-smaller" class="secondary-button" aria-label="缩小 PDF">−</button><span id="selection-pdf-zoom">100%</span><button id="selection-pdf-larger" class="secondary-button" aria-label="放大 PDF">＋</button><button id="selection-pdf-fit" class="text-button">适应宽度</button><button id="selection-pdf-original" class="text-button">打开原始 PDF ↗</button><button id="selection-pdf-glossary" class="text-button">专业术语表</button></div>
  <p id="selection-pdf-status" role="status">选中词语或句子，再点击「翻译」。</p>
  <div class="selection-pdf-workspace"><button id="selection-pdf-prev" class="selection-pdf-arrow prev" aria-label="PDF 上一页">‹</button><div id="selection-pdf-scroll"><div id="selection-pdf-page"></div></div><button id="selection-pdf-next" class="selection-pdf-arrow next" aria-label="PDF 下一页">›</button></div>
</section>`);

async function openSelectionReader(item, pdf, initialPage = 1) {
  if (window.selectionPdfView) closeSelectionReader();
  dismissSelectionTranslation();
  window.getSelection()?.removeAllRanges();
  const view = {item, pdf, page:Number.isInteger(initialPage) && initialPage > 0 ? initialPage : 1, zoom:1, revision:0, document:null, renderTask:null};
  window.selectionPdfView = view;
  $('#selection-pdf-title').textContent = item.title;
  $('#selection-pdf-reader').hidden = false;
  document.body.classList.add('pdf-reading');
  $('#selection-pdf-page').replaceChildren();
  $('#selection-pdf-status').textContent = '正在加载原始 PDF 和可选中文字层…';
  try {
    pdfJsModule ||= await import('/static/vendor/pdfjs/build/pdf.mjs');
    pdfJsModule.GlobalWorkerOptions.workerSrc = '/static/vendor/pdfjs/build/pdf.worker.mjs';
    if (window.selectionPdfView !== view) return;
    view.loadingTask = pdfJsModule.getDocument({url:`/api/attachments/${pdf.key}/file`,
      cMapUrl:'/static/vendor/pdfjs/cmaps/',cMapPacked:true,standardFontDataUrl:'/static/vendor/pdfjs/standard_fonts/',
      wasmUrl:'/static/vendor/pdfjs/wasm/',iccUrl:'/static/vendor/pdfjs/iccs/',
      isEvalSupported:false,enableXfa:false});
    view.document = await view.loadingTask.promise;
    if (window.selectionPdfView !== view) return;
    view.page = Math.min(view.page, view.document.numPages);
    $('#selection-pdf-count').textContent = view.document.numPages;
    $('#selection-pdf-number').max = view.document.numPages;
    await renderSelectionPdf(view);
  } catch(error) {
    if(window.selectionPdfView===view) $('#selection-pdf-status').textContent = `PDF 加载失败：${error.message}。可点击「打开原始 PDF」阅读。`;
  }
}

async function renderSelectionPdf(view = window.selectionPdfView) {
  if(!view?.document || window.selectionPdfView!==view) return;
  const revision = ++view.revision;
  view.renderTask?.cancel();
  $('#selection-translate').hidden = true;
  $('#selection-pdf-number').value = view.page;
  $('#selection-pdf-zoom').textContent = `${Math.round(view.zoom*100)}%`;
  $('#selection-pdf-prev').disabled = view.page<=1;
  $('#selection-pdf-next').disabled = view.page>=view.document.numPages;
  try {
    const pdfPage = await view.document.getPage(view.page);
    if(window.selectionPdfView!==view || revision!==view.revision) return;
    const original = pdfPage.getViewport({scale:1});
    const width = Math.max(200, Math.min(1150, $('#selection-pdf-scroll').clientWidth - 40));
    const scale = width / original.width * view.zoom;
    const viewport = pdfPage.getViewport({scale});
    const canvas = document.createElement('canvas');
    const ratio = Math.min(devicePixelRatio || 1,2);
    canvas.width = Math.floor(viewport.width*ratio);canvas.height = Math.floor(viewport.height*ratio);
    canvas.style.width = `${viewport.width}px`;canvas.style.height = `${viewport.height}px`;
    const layer = document.createElement('div');layer.className='textLayer';
    const page = $('#selection-pdf-page');
    page.style.width = `${viewport.width}px`;page.style.height = `${viewport.height}px`;
    page.style.setProperty('--total-scale-factor',scale);
    page.replaceChildren(canvas,layer);
    view.renderTask = pdfPage.render({canvasContext:canvas.getContext('2d'),viewport,transform:[ratio,0,0,ratio,0,0]});
    await view.renderTask.promise;
    if(window.selectionPdfView!==view || revision!==view.revision) return;
    const textContent = await pdfPage.getTextContent();
    if(window.selectionPdfView!==view || revision!==view.revision) return;
    await new pdfJsModule.TextLayer({textContentSource:textContent,container:layer,viewport}).render();
    if(window.selectionPdfView!==view || revision!==view.revision) return;
    $('#selection-pdf-status').textContent = textContent.items.some(t=>t.str?.trim())
      ? '选中词语或句子，再点击「翻译」。术语表和已存译文免费；新译文会保存到当前文献。'
      : '本页没有可选中文字，可能是扫描页。可阅读原图；当前划词功能需要 PDF 文字层。';
  } catch(error) {
    if(error.name!=='RenderingCancelledException' && window.selectionPdfView===view && revision===view.revision)
      $('#selection-pdf-status').textContent=`此页显示失败：${error.message}。可打开原始 PDF。`;
  }
}

function closeSelectionReader() {
  const view = window.selectionPdfView;
  window.selectionPdfView=null;
  if(view) {view.revision++;view.renderTask?.cancel();view.loadingTask?.destroy();}
  $('#selection-pdf-reader').hidden=true;
  document.body.classList.remove('pdf-reading');
  dismissSelectionTranslation();
}

function turnSelectionPdf(delta) {
  const view=window.selectionPdfView;
  if(!view?.document) return;
  view.page=Math.max(1,Math.min(view.document.numPages,view.page+delta));
  $('#selection-pdf-scroll').scrollTop=0;
  renderSelectionPdf(view);
}
$('#selection-pdf-close').onclick=closeSelectionReader;
$('#selection-pdf-prev').onclick=()=>turnSelectionPdf(-1);
$('#selection-pdf-next').onclick=()=>turnSelectionPdf(1);
$('#selection-pdf-number').onchange=event=>{
  const view=window.selectionPdfView;
  if(!view?.document) return;
  const page=Number(event.target.value);
  if(!Number.isInteger(page)||page<1||page>view.document.numPages){event.target.value=view.page;return;}
  turnSelectionPdf(page-view.page);
};
for(const [id,delta] of [['selection-pdf-smaller',-.2],['selection-pdf-larger',.2]]) $('#'+id).onclick=()=>{
  const view=window.selectionPdfView;if(view){view.zoom=Math.max(.4,Math.min(3,view.zoom+delta));renderSelectionPdf(view);}
};
$('#selection-pdf-fit').onclick=()=>{if(window.selectionPdfView){selectionPdfView.zoom=1;renderSelectionPdf();}};
$('#selection-pdf-original').onclick=()=>{if(window.selectionPdfView)window.open(`/api/attachments/${selectionPdfView.pdf.key}/file#page=${selectionPdfView.page}`,'_blank','noopener');};
$('#selection-pdf-glossary').onclick=openTerminology;
let pdfResizeTimer;
new ResizeObserver(()=>{clearTimeout(pdfResizeTimer);pdfResizeTimer=setTimeout(()=>renderSelectionPdf(),150);}).observe($('#selection-pdf-scroll'));
window.addEventListener('hashchange',closeSelectionReader);
document.addEventListener('keydown',event=>{
  if(!window.selectionPdfView||event.target.closest('input,textarea,select')||!$('#terminology-modal').classList.contains('hidden')||!$('#translation-panel').hidden)return;
  if(event.key==='ArrowLeft'){event.preventDefault();turnSelectionPdf(-1);}
  if(event.key==='ArrowRight'){event.preventDefault();turnSelectionPdf(1);}
});
