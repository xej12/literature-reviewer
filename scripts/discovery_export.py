"""Export only explicitly selected cached candidates. No network or Zotero writes."""
from datetime import datetime, timezone
import html
import re
from urllib.parse import quote

import discovery as d
import discovery_joint as joint

FORMATS = {'ris': ('ris', 'application/x-research-info-systems'),
           'bibtex': ('bib', 'application/x-bibtex'), 'markdown': ('md', 'text/markdown')}


def clean(value):
    return ' '.join(''.join(c for c in str(value or '') if ord(c) >= 32 or c in '\r\n\t').split())


def bib_text(value):
    escapes = {'\\':r'\textbackslash{}', '{':r'\{', '}':r'\}', '&':r'\&', '%':r'\%',
               '$':r'\$', '#':r'\#', '_':r'\_', '~':r'\textasciitilde{}', '^':r'\textasciicircum{}'}
    return ''.join(escapes.get(c, c) for c in clean(value))


def md_text(value):
    return re.sub(r'([\\`*_{}\[\]()#+.!|])', r'\\\1', html.escape(clean(value), quote=False))


def url(value):
    safe = d.safe_url(value)
    return quote(safe, safe=":/?#@!$&'*+,;=%-._~") if safe else ''


def metadata(hit):
    year = clean(hit.get('year'))
    return {'title':clean(hit.get('title')), 'authors':[clean(a) for a in hit.get('creators', []) if clean(a)],
            'year':year if re.fullmatch(r'\d{4}',year) else '', 'venue':clean(hit.get('publicationTitle')),
            'doi':d.doi(hit.get('doi')), 'url':url(hit.get('url')), 'oa':url(hit.get('oaUrl')),
            'abstract':clean(hit.get('abstract')), 'sources':', '.join(clean(s) for s in hit.get('sources', []))}


def ris(hits):
    records=[]
    for hit in hits:
        m=metadata(hit)
        # Generic records preserve the source metadata without guessing publication type.
        fields=[('TY','GEN'),('TI',m['title'])]
        fields.extend(('AU',author) for author in m['authors'])
        fields.extend((tag,m[field]) for tag,field in [('PY','year'),('T2','venue'),('DO','doi'),('UR','url'),('AB','abstract')] if m[field])
        if m['oa'] and m['oa'] != m['url']:fields.append(('N1','Open access: '+m['oa']))
        if m['sources']:fields.append(('N1','Data sources: '+m['sources']))
        fields.append(('ER',''))
        records.append('\n'.join(f'{tag}  - {value}' for tag,value in fields))
    return '\n\n'.join(records)+'\n'


def bibtex(hits):
    records=[]
    for hit in hits:
        m=metadata(hit)
        # Full names are literal author names; do not infer surnames or invent metadata.
        fields=[('title','{'+bib_text(m['title'])+'}')]
        if m['authors']:fields.append(('author',' and '.join('{'+bib_text(a)+'}' for a in m['authors'])))
        fields.extend((name,m[field] if name=='url' else bib_text(m[field])) for name,field in [('year','year'),('howpublished','venue'),('doi','doi'),('url','url'),('abstract','abstract')] if m[field])
        note=[]
        if m['sources']:note.append('Data sources: '+m['sources'])
        if m['oa'] and m['oa'] != m['url']:note.append('Open access: '+m['oa'])
        if note:fields.append(('note',bib_text('; '.join(note))))
        records.append('@misc{lr_'+d.result_id(hit)+',\n'+',\n'.join('  '+name+' = {'+value+'}' for name,value in fields)+'\n}')
    return '\n\n'.join(records)+'\n'


def markdown(hits,value):
    params=value.get('parameters') or {}
    seeds=value.get('seeds') or ([value['seed']] if value.get('seed') else [])
    lines=['# 待读文献清单','',f'导出 {len(hits)} 篇已选候选。元数据来自学术服务，推荐关系尚未逐篇核对全文。','']
    if params.get('question'):lines.extend(['研究问题：'+md_text(params['question']),''])
    if params.get('keywords'):lines.extend(['检索词：'+md_text(params['keywords']),''])
    if seeds:lines.extend(['起始论文：'+'；'.join(md_text(s.get('title')) for s in seeds),''])
    if value.get('searchedAt'):lines.extend(['检索时间：'+md_text(value['searchedAt']),''])
    if value.get('stale'):lines.extend(['提示：这些结果沿用了部分旧资料，导出未重新检索。',''])
    for index,hit in enumerate(hits,1):
        m=metadata(hit)
        lines.extend([f'## {index}. '+md_text(m['title']),''])
        if m['authors']:lines.extend(['作者：'+'；'.join(md_text(a) for a in m['authors']),''])
        if m['year'] or m['venue']:lines.extend(['年份 / 来源：'+md_text(' · '.join(s for s in (m['year'],m['venue']) if s)),''])
        if m['doi']:lines.extend(['DOI：'+md_text(m['doi']),''])
        if m['url']:lines.extend(['[DOI / 原文](<'+m['url']+'>)',''])
        if m['oa'] and m['oa']!=m['url']:lines.extend(['[开放获取](<'+m['oa']+'>)',''])
        if m['sources']:lines.extend(['数据源：'+md_text(m['sources']),''])
        evidence=list(dict.fromkeys(clean(r.get('source'))+' · '+clean(r.get('text'))+('；关联起点：'+clean(r['seedTitle']) if r.get('seedTitle') else '') for r in hit.get('relations',[])))
        if evidence:lines.extend(['关联依据：','']+['- '+md_text(e) for e in evidence]+[''])
        if m['abstract']:lines.extend(['### 摘要','',md_text(m['abstract']),''])
        lines.extend(['### 我的阅读笔记','','- 阅读目标：','- 核心发现：','- 待核对的问题：',''])
    return '\n'.join(lines)


def export(payload,library):
    if not isinstance(payload,dict) or not isinstance(payload.get('format'),str) or payload['format'] not in FORMATS:
        raise ValueError('请选择 RIS、BibTeX 或 Markdown 格式')
    identifiers=payload.get('resultIds')
    if not isinstance(identifiers,list) or not 1<=len(identifiers)<=60 or any(not isinstance(i,str) or not re.fullmatch(r'[a-f0-9]{64}',i) for i in identifiers):
        raise ValueError('请勾选 1–60 篇文献后导出')
    if len(set(identifiers))!=len(identifiers):raise ValueError('导出文献编号重复')
    if bool(payload.get('groupId'))==bool(payload.get('itemKey')):
        raise ValueError('请指定一组已保存的检索结果')
    if payload.get('groupId'):
        value=joint.load(payload['groupId'],library)
    else:
        key=payload['itemKey']
        d._path({'key':key})  # Validate before resolving a local library key.
        item=next((item for item in library if item['key']==key),None)
        if not item:raise FileNotFoundError('起始文献不存在')
        value=d.cached(item)
    if not value.get('saved'):raise ValueError('请先完成检索并保存结果，再导出')
    available={d.result_id(h):h for h in value['results']}
    if any(i not in available for i in identifiers):
        raise ValueError('部分已选文献已不在当前保存结果中，请重新打开结果后勾选；不会自动重新检索')
    if any(available[i].get('excluded') for i in identifiers):
        raise ValueError('已标记不感兴趣的文献不能导出，请先恢复该文献')
    # Follow the saved ranking, independent of checkbox click order.
    hits=[h for h in value['results'] if d.result_id(h) in set(identifiers)]
    format_name=payload['format']
    content=markdown(hits,value) if format_name=='markdown' else bibtex(hits) if format_name=='bibtex' else ris(hits)
    extension,mime=FORMATS[format_name]
    return {'content':content,'filename':'related-literature-'+datetime.now(timezone.utc).strftime('%Y%m%d')+'.'+extension,
            'mimeType':mime+'; charset=utf-8','count':len(hits)}
