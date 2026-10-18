"""Single-paper discovery via public scholarly APIs; no LLM or Zotero writes.

Independent adapters based on the public OpenAlex and Semantic Scholar APIs.
See references/discovery-research.md for upstream design references.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import threading
import unicodedata
import urllib.error
import urllib.request
from urllib.parse import quote, urlencode, urlparse, unquote
import request_jobs

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / 'data/discovery'
SETTINGS_PATH = ROOT / 'data/discovery-settings.json'
LOCK = threading.RLock()
SEARCH_LOCKS = {}
NAMES = ('OpenAlex', 'Semantic Scholar')
KINDS = {'similar': '相似研究', 'reference': '前置文献', 'citing': '后续研究'}
FIELDS = 'paperId,title,authors,year,venue,abstract,externalIds,url,openAccessPdf,citationCount,publicationTypes,isOpenAccess'
OA_FIELDS = 'id,doi,title,publication_year,authorships,primary_location,best_oa_location,open_access,abstract_inverted_index,cited_by_count,ids,type'


class SourceError(RuntimeError):
    pass


def _atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def settings():
    try:
        value = json.loads(SETTINGS_PATH.read_text(encoding='utf-8'))
        if not isinstance(value, dict) or any(not isinstance(value.get(name, ''), str) for name in ('openalexKey', 'semanticScholarKey')):
            raise ValueError('检索服务配置文件格式异常，请检查备份')
        return {name: value.get(name, '') for name in ('openalexKey', 'semanticScholarKey')}
    except FileNotFoundError:
        return {'openalexKey': '', 'semanticScholarKey': ''}


def public_settings():
    saved = settings()
    return {'openalexConfigured': bool(saved['openalexKey']), 'semanticScholarConfigured': bool(saved['semanticScholarKey'])}


def save_settings(payload):
    if not isinstance(payload, dict):
        raise ValueError('请提供检索服务配置')
    with LOCK:
        saved = settings()
        for name in ('openalexKey', 'semanticScholarKey'):
            value = payload.get(name, '')
            if not isinstance(value, str) or len(value) > 500 or any(c in value for c in '\r\n'):
                raise ValueError('检索服务 Key 格式无效')
            if payload.get('clear' + name[0].upper() + name[1:]) is True:
                saved[name] = ''
            elif value.strip():
                saved[name] = value.strip()
        _atomic(SETTINGS_PATH, saved)
        return public_settings()


def title_key(value):
    return ''.join(c for c in unicodedata.normalize('NFKC', str(value or '')).casefold() if c.isalnum())


def doi(value):
    match = re.search(r'10\.\d{4,9}/[^\s?#<>\"]+', unquote(str(value or '')), re.I)
    return match[0].rstrip('.,;').casefold() if match else ''


def arxiv(value):
    match = re.search(r'(?:arxiv[:\s]+|arxiv\.org/(?:abs|pdf)/)([a-z.-]+/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?', str(value or ''), re.I)
    return match[1].casefold() if match else ''


def safe_url(value):
    value = str(value or '')
    try:
        parsed = urlparse(value)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
            return ''
        if any(c.isspace() or ord(c) < 32 for c in value):
            return ''
        return value
    except ValueError:
        return ''


def _request(source, path, params, config, body=None):
    headers = {'User-Agent': 'LiteratureReviewer/1.0 (https://github.com/xej12/literature-reviewer)', 'Accept': 'application/json'}
    params = dict(params)
    if source == 'OpenAlex':
        base = 'https://api.openalex.org'
        if config['openalexKey']:
            params['api_key'] = config['openalexKey']
    else:
        base = 'https://api.semanticscholar.org'
        if config['semanticScholarKey']:
            headers['x-api-key'] = config['semanticScholarKey']
    url = base + path + ('?' + urlencode(params) if params else '')
    if body is not None:
        headers['Content-Type'] = 'application/json'
    try:
        with request_jobs.urlopen(urllib.request.Request(url, headers=headers, data=json.dumps(body).encode('utf-8') if body is not None else None), timeout=12) as response:
            try:
                data = response.read(4_000_001)
            finally:
                request_jobs.check()
            if len(data) > 4_000_000:
                raise SourceError('答复过大，请稍后缩小范围重试')
            value = json.loads(data)
            if not isinstance(value, dict):
                raise SourceError('服务答复格式异常')
            return value
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        if code == 404:
            return None
        if code in (401, 403):
            raise SourceError('服务拒绝访问，请在检索设置中检查 Key 或账户权限') from None
        if code == 429:
            raise SourceError('服务限流或额度已用完，请稍后重试或配置 Key') from None
        raise SourceError(f'服务返回 HTTP {code}') from None
    except (OSError, urllib.error.URLError):
        request_jobs.check()
        # Never echo exception URLs: OpenAlex credentials are query parameters.
        raise SourceError('无法连接或请求超时，请检查网络、代理或稍后重试') from None
    except (ValueError, TypeError):
        raise SourceError('服务答复格式异常') from None


def _abstract(index):
    if not isinstance(index, dict):
        return ''
    words = {}
    for word, positions in index.items():
        if not isinstance(positions, list):
            continue
        for position in positions:
            if type(position) is int and 0 <= position < 5000:
                words[position] = str(word)
    return ' '.join(words[p] for p in sorted(words))[:12000]


def normalize(source, raw):
    if source == 'OpenAlex':
        venue = (raw.get('primary_location') or {}).get('source') or {}
        oa = raw.get('best_oa_location') or {}
        item = {'sourceId': raw.get('id', ''), 'title': raw.get('title') or raw.get('display_name') or '',
                'creators': [(a.get('author') or {}).get('display_name', '') for a in raw.get('authorships') or []],
                'year': raw.get('publication_year'), 'publicationTitle': venue.get('display_name', ''),
                'doi': doi(raw.get('doi')), 'abstract': _abstract(raw.get('abstract_inverted_index')),
                'url': safe_url((raw.get('primary_location') or {}).get('landing_page_url')) or safe_url(raw.get('id')),
                'oaUrl': safe_url(oa.get('pdf_url') or oa.get('landing_page_url') or (raw.get('open_access') or {}).get('oa_url')),
                'citationCount': raw.get('cited_by_count', 0)}
    else:
        ids = raw.get('externalIds') or {}
        item = {'sourceId': raw.get('paperId', ''), 'title': raw.get('title', ''),
                'creators': [a.get('name', '') for a in raw.get('authors') or []], 'year': raw.get('year'),
                'publicationTitle': raw.get('venue', ''), 'doi': doi(ids.get('DOI')), 'abstract': raw.get('abstract') or '',
                'url': safe_url(raw.get('url')), 'oaUrl': safe_url((raw.get('openAccessPdf') or {}).get('url')),
                'citationCount': raw.get('citationCount', 0)}
        if ids.get('ArXiv'):
            item['arxiv'] = str(ids['ArXiv']).casefold()
    item['arxiv'] = item.get('arxiv') or arxiv(item['url']) or arxiv(item['oaUrl'])
    if source == 'OpenAlex':
        item['isReview'] = raw.get('type') == 'review' if raw.get('type') else None
        item['isOpenAccess'] = (raw.get('open_access') or {}).get('is_oa') is True or bool(item['oaUrl'])
    else:
        item['isReview'] = 'Review' in raw['publicationTypes'] if isinstance(raw.get('publicationTypes'), list) else None
        item['isOpenAccess'] = raw.get('isOpenAccess') is True or bool(item['oaUrl'])
    item['source'] = source
    if item['doi']:
        item['url'] = 'https://doi.org/' + quote(item['doi'], safe='/():;')
    item['title'] = str(item['title'])[:1000]
    return item


def _year(value):
    match = re.search(r'\b(?:19|20)\d{2}\b', str(value or ''))
    return match[0] if match else ''


def same_paper(a, b):
    ad, bd = doi(a.get('doi')) or doi(a.get('url')), doi(b.get('doi')) or doi(b.get('url'))
    if ad and bd:
        return ad == bd
    aa_id, ba_id = a.get('arxiv') or arxiv(a.get('url')) or arxiv(a.get('extra')), b.get('arxiv') or arxiv(b.get('url')) or arxiv(b.get('extra'))
    if aa_id and ba_id and aa_id == ba_id:
        return True
    key = title_key(a.get('title'))
    ay, by = _year(a.get('year') or a.get('date')), _year(b.get('year') or b.get('date'))
    # A short title, different years or no shared author is not enough to merge.
    aa = {title_key(x) for x in a.get('creators', []) if title_key(x)}
    ba = {title_key(x) for x in b.get('creators', []) if title_key(x)}
    return bool(len(key) >= 20 and key == title_key(b.get('title')) and ay and ay == by and aa & ba)


def _identifier(source, identifier):
    pattern = r'(?:https://openalex.org/)?(W\d+)' if source == 'OpenAlex' else r'([a-f0-9]{40}|\d+)'
    match = re.fullmatch(pattern, str(identifier or ''))
    if not match:
        raise ValueError('无效的论文匹配编号')
    return match[1]


def same_record(a, b):
    """Shared provider IDs can fill missing identity, never override DOI conflicts."""
    ad, bd = doi(a.get('doi')) or doi(a.get('url')), doi(b.get('doi')) or doi(b.get('url'))
    if ad and bd and ad != bd:
        return False
    return same_paper(a, b) or bool(a.get('sourceId') and a.get('source') == b.get('source') and a['sourceId'] == b.get('sourceId'))


def _resolve(source, item, config, selected=None):
    known_doi = doi(item.get('doi')) or doi(item.get('url'))
    arxiv_id = arxiv(item.get('url')) or arxiv(item.get('extra'))
    identifier = None
    if selected and selected.get('source') == source:
        identifier = _identifier(source, selected.get('id'))
    elif known_doi:
        identifier = 'https://doi.org/' + known_doi if source == 'OpenAlex' else 'DOI:' + known_doi
    elif source == 'Semantic Scholar' and arxiv_id:
        identifier = 'ARXIV:' + arxiv_id
    if identifier:
        path = '/works/' if source == 'OpenAlex' else '/graph/v1/paper/'
        data = _request(source, path + quote(identifier, safe=''), {} if source == 'OpenAlex' else {'fields': FIELDS}, config)
        if data:
            normalized = normalize(source, data)
            if selected or not known_doi or normalized['doi'] == known_doi:
                return data, normalized, []
    title = str(item.get('title', '')).strip()[:500]
    if not title:
        return None, None, []
    if source == 'OpenAlex':
        data = _request(source, '/works', {'search': title, 'per-page': 5, 'select': OA_FIELDS}, config)
        rows = (data or {}).get('results') or []
    else:
        data = _request(source, '/graph/v1/paper/search', {'query': title, 'limit': 5, 'fields': FIELDS}, config)
        rows = (data or {}).get('data') or []
    candidates = [normalize(source, row) for row in rows if row.get('title') or row.get('display_name')]
    # DOI lookup failures never silently switch to a different DOI on title alone.
    exact = [(row, normalize(source, row)) for row in rows if same_paper(item, normalize(source, row))]
    if len(exact) == 1:
        raw, normalized = exact[0]
        if source == 'OpenAlex':
            raw = _request(source, '/works/' + _identifier(source, normalized['sourceId']), {}, config)
        return raw, normalized, []
    return None, None, candidates


def _collect(source, item, config, selected):
    result = {'source': source, 'match': None, 'candidates': [], 'hits': [], 'warnings': [], 'completed': 0}
    if selected and selected['source'] != source:
        result['warnings'].append('本次仅按你确认的数据源检索，避免混用未确认的起始论文')
        return result
    try:
        raw, matched, candidates = _resolve(source, item, config, selected)
        result.update(match=matched, candidates=candidates)
    except SourceError as exc:
        result['warnings'].append(str(exc))
        return result
    if not matched:
        result['warnings'].append('未准确匹配起始论文，请核对候选或补充 DOI')
        return result
    identifier = _identifier(source, matched['sourceId'])
    for kind in KINDS:
        try:
            if source == 'OpenAlex':
                params = {'per-page': 20, 'select': OA_FIELDS}
                if kind == 'reference':
                    ids = [_identifier(source, value) for value in (raw.get('referenced_works') or [])[:30]]
                    data = _request(source, '/works', {**params, 'filter': 'openalex:' + '|'.join(ids)}, config) if ids else {}
                elif kind == 'citing':
                    data = _request(source, '/works', {**params, 'filter': 'cites:' + identifier, 'sort': 'publication_date:desc'}, config)
                else:
                    query = (matched['title'] + '\n' + matched['abstract'])[:1600]
                    try:
                        data = _request(source, '/works', {**params, 'search.semantic': query}, config)
                    except SourceError:
                        # Keyword fallback is labelled; do not call it semantic similarity.
                        words = re.findall(r'[A-Za-z][A-Za-z-]{2,}', matched['title'])
                        query = ' '.join(w for w in words if w.lower() not in {'the','and','for','with','from','using','based'})[:180] or matched['title'][:180]
                        data = _request(source, '/works', {**params, 'search': query}, config)
                        result['warnings'].append('语义检索不可用，相似研究已降级为标题关键词检索')
                rows = (data or {}).get('results') or []
            else:
                if kind == 'similar':
                    data = _request(source, '/recommendations/v1/papers/forpaper/' + identifier, {'fields': FIELDS, 'limit': 20}, config)
                    rows = (data or {}).get('recommendedPapers') or []
                else:
                    endpoint, key = ('references', 'citedPaper') if kind == 'reference' else ('citations', 'citingPaper')
                    data = _request(source, '/graph/v1/paper/' + identifier + '/' + endpoint, {'fields': FIELDS, 'limit': 20}, config)
                    rows = [r.get(key) for r in (data or {}).get('data') or [] if r.get(key)]
            if data is None:
                raise SourceError('该服务未提供此项数据')
            result['completed'] += 1
            for rank, row in enumerate(rows):
                hit = normalize(source, row)
                if not hit['title'] or same_paper(matched, hit):
                    continue
                reason = {'kind': kind, 'source': source, 'rank': rank + 1,
                          'text': '被该数据源作为相似候选返回；尚未核对全文' if kind == 'similar' else
                          '起始论文的参考文献' if kind == 'reference' else '该论文引用了起始论文',
                          'seedTitle': matched['title']}
                if kind == 'similar' and source == 'OpenAlex' and any('降级' in w for w in result['warnings']):
                    reason['text'] = '标题关键词检索命中；相似程度需自行核对'
                hit['relations'] = [reason]
                result['hits'].append(hit)
        except SourceError as exc:
            result['warnings'].append(KINDS[kind] + '：' + str(exc))
    return result


def _safe_collect(source, item, config, selected):
    try:
        return _collect(source, item, config, selected)
    except (ValueError, KeyError, TypeError, AttributeError):
        return {'source': source, 'match': None, 'candidates': [], 'hits': [],
                'warnings': ['服务答复格式异常，其他来源结果仍可使用'], 'completed': 0}


def merge_results(batches, item):
    merged = []
    for batch in batches:
        for hit in batch['hits']:
            if same_paper(item, hit):
                continue
            existing = next((x for x in merged if same_record(x, hit)), None)
            if existing:
                existing['relations'].extend(r for r in hit['relations'] if r not in existing['relations'])
                for field in ('doi', 'abstract', 'oaUrl', 'arxiv'):
                    if not existing.get(field) and hit.get(field):
                        existing[field] = hit[field]
                for field in ('isReview', 'isOpenAccess'):
                    if hit.get(field) is True:
                        existing[field] = True
                if existing.get('doi'):
                    existing['url'] = 'https://doi.org/' + quote(existing['doi'], safe='/():;')
                if hit['source'] not in existing['sources']:
                    existing['sources'].append(hit['source'])
            else:
                merged.append({**hit, 'sources': [hit['source']]})
    for hit in merged:
        # Reciprocal ranks combine heterogeneous providers without fake percentages.
        hit['_rank'] = sum(1 / (60 + r['rank']) for r in hit['relations'])
    merged.sort(key=lambda x: x['_rank'], reverse=True)
    # Preserve a few of each relationship instead of allowing one pool to fill all slots.
    chosen = []
    for kind in KINDS:
        chosen.extend(x for x in [h for h in merged if any(r['kind'] == kind for r in h['relations'])][:5] if x not in chosen)
    chosen.extend(x for x in merged if x not in chosen)
    chosen = sorted(chosen[:20], key=lambda x: x['_rank'], reverse=True)
    for hit in chosen:
        hit.pop('_rank', None)
    return chosen


def _path(item):
    key = str(item.get('key', ''))
    if not re.fullmatch(r'[A-Z0-9]{1,64}', key):
        raise ValueError('无效的文献编号')
    return CACHE_DIR / (key + '.json')


def fingerprint(item):
    data = {k: item.get(k) for k in ('doi', 'url', 'title', 'date', 'creators', 'abstract')}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def result_id(hit):
    identity = {'doi': hit['doi']} if hit.get('doi') else {'arxiv': hit['arxiv']} if hit.get('arxiv') else {'source':hit['source'],'id':hit['sourceId']}
    return hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def cached(item):
    with LOCK:
        path = _path(item)
        if not path.exists():
            return {'saved': False, 'results': [], 'providers': [], 'candidates': []}
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(value, dict) or not isinstance(value.get('results'), list):
                raise ValueError()
        except (OSError, ValueError):
            raise ValueError('已保存检索文件无法读取，原文件已保留，请检查备份') from None
        return {**value, 'saved': True, 'cached': True, 'stale': value.get('fingerprint') != fingerprint(item)}


def discover(item, force=False, selected=None):
    if type(force) is not bool:
        raise ValueError('刷新参数无效')
    if selected is not None:
        if not isinstance(selected, dict) or selected.get('source') not in NAMES:
            raise ValueError('无效的候选论文')
        _identifier(selected['source'], selected.get('id'))
    with LOCK:
        lock = SEARCH_LOCKS.setdefault(str(_path(item)), threading.Lock())
    with lock:
        request_jobs.check()
        previous = cached(item)
        if previous['saved'] and not force:
            return previous
        if not selected and not previous.get('stale'):
            selected = previous.get('selection')
        config = settings()
        # Two providers run independently; one failure must not erase the other's results.
        with ThreadPoolExecutor(max_workers=2) as pool:
            worker = request_jobs.inherit_context(_safe_collect)
            futures = [pool.submit(worker, source, item, config, selected) for source in NAMES]
            batches = [future.result() for future in futures]
        results = merge_results(batches, item)
        providers = [{k: batch[k] for k in ('source', 'match', 'warnings', 'completed')} for batch in batches]
        candidates = [candidate for batch in batches for candidate in batch['candidates']]
        now = datetime.now(timezone.utc).isoformat()
        value = {'saved': False, 'cached': False, 'stale': False, 'fingerprint': fingerprint(item), 'searchedAt': now,
                 'results': results, 'providers': providers, 'candidates': candidates,
                 'seed': {k: item.get(k) for k in ('key', 'title', 'doi', 'date')}}
        if selected:
            value['selection'] = selected
        # Empty/failed refreshes preserve previous useful results. Unresolved matches aren't cached.
        if previous['saved'] and not results and any(b['warnings'] for b in batches):
            return {**previous, 'preserved': True, 'latestAttempt': {'searchedAt': now, 'providers': providers, 'candidates': candidates}}
        if any(b['completed'] for b in batches):
            with LOCK:
                request_jobs.check()
                _atomic(_path(item), value)
            value['saved'] = True
        return value


def with_library(value, items):
    result = {**value, 'results': []}
    for hit in value.get('results', []):
        match = next((i for i in items if same_paper(hit, {**i, 'doi': doi(i.get('doi')) or doi(i.get('url')), 'arxiv': arxiv(i.get('url'))})), None)
        result['results'].append({**hit, 'resultId':result_id(hit), 'inLibrary': bool(match), 'libraryKey': match.get('key') if match else None})
    return result
