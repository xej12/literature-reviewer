"""Cached multi-seed discovery with explicit question evidence; no LLM calls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import re
import threading

import discovery as d
import reading_priority
import request_jobs
import translation

LOCKS = {}
STOPWORDS = set('the and for with from using based what how which compare comparison research study find looking papers about are can does this that into methods method more'.split())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def parameters(payload):
    if not isinstance(payload, dict):
        raise ValueError('无效的联合检索请求')
    keys = payload.get('itemKeys')
    if not isinstance(keys, list) or not 2 <= len(keys) <= 5 or any(not isinstance(k, str) or not re.fullmatch(r'[A-Z0-9]{1,64}', k) for k in keys):
        raise ValueError('请选择 2–5 篇起始论文')
    if len(set(keys)) != len(keys):
        raise ValueError('起始论文不能重复')
    value = {'itemKeys': sorted(keys)}
    for name, maximum in [('question', 1000), ('keywords', 300)]:
        text = payload.get(name, '')
        if not isinstance(text, str) or len(text) > maximum:
            raise ValueError('研究问题或检索词过长')
        value[name] = ' '.join(text.split())
    return value


def validate_items(items, params):
    mapping = {item['key']: item for item in items}
    if any(k not in mapping for k in params['itemKeys']):
        raise FileNotFoundError('所选起始论文已不在文献库，请重新选择；已有结果仍保留')
    seeds = [mapping[k] for k in params['itemKeys']]
    for index, seed in enumerate(seeds):
        if any(d.same_paper(seed, other) for other in seeds[:index]):
            raise ValueError('所选条目包含同一篇论文，请选择不同的论文')
    return seeds


def query_plan(params):
    question, keywords = params['question'], params['keywords']
    expanded = []
    if question and not keywords:
        for entry in translation.glossary()['entries']:
            if entry.get('translation') and entry['translation'] in question:
                expanded.append(entry['term'])
        for line in reading_priority.profile()['topics'].splitlines():
            parts = [part.strip() for part in line.split('|') if part.strip()]
            if any(part.casefold() in question.casefold() for part in parts):
                expanded.extend(part for part in parts if re.search(r'[a-zA-Z]', part) and not re.search(r'[\u4e00-\u9fff]', part))
    english = [word for word in re.findall(r'[A-Za-z][A-Za-z0-9-]{2,}', question) if word.casefold() not in STOPWORDS]
    words = list(dict.fromkeys([*expanded, *english]))[:12]
    keyword_query = keywords or ' '.join(words) or question
    semantic_query = keywords or (question + ('\nKeywords: ' + ' '.join(expanded) if expanded else ''))
    return {'query': keyword_query[:500], 'semanticQuery': semantic_query[:1600], 'expandedTerms': list(dict.fromkeys(expanded))[:12],
            'notice': '中文问题未命中本电脑术语或同义词，补充英文检索词可改善关键词降级检索。' if question and not keywords and not words and re.search(r'[\u4e00-\u9fff]', question) else ''}


def _path(group_id):
    if not re.fullmatch(r'[a-f0-9]{64}', str(group_id)):
        raise ValueError('无效的联合检索编号')
    return d.CACHE_DIR / 'groups' / (group_id + '.json')


def _fingerprint(seeds, plan):
    return digest({'version': 1, 'seeds': {i['key']: d.fingerprint(i) for i in seeds}, 'plan': plan})


def _feedback(group_id):
    path = _path(group_id).with_suffix('.feedback.json')
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (OSError, ValueError):
        raise ValueError('本组不感兴趣记录无法读取，原文件已保留') from None


def _annotate(value):
    feedback = _feedback(value['id'])
    return {**value, 'results': [{**hit, 'excluded': feedback.get(hit['resultId']) is True} for hit in value['results']]}


def load(group_id, library):
    path = _path(group_id)
    if not path.exists():
        raise FileNotFoundError('尚未保存这组联合检索')
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict) or value.get('id') != group_id or not isinstance(value.get('results'), list):
            raise ValueError()
    except (OSError, ValueError):
        raise ValueError('联合检索文件无法读取，原文件已保留，请检查备份') from None
    params = parameters(value['parameters'])
    mapping = {i['key']: i for i in library}
    missing = [k for k in params['itemKeys'] if k not in mapping]
    seeds = [mapping[k] for k in params['itemKeys'] if k in mapping]
    stale = bool(missing or value.get('staleSeedKeys')) or _fingerprint(seeds, query_plan(params)) != value['fingerprint']
    return d.with_library(_annotate({**value, 'saved': True, 'cached': True, 'stale': stale, 'missingSeedKeys': missing}), library)


def history():
    entries, unreadable = [], 0
    for path in (d.CACHE_DIR / 'groups').glob('*.json'):
        if path.name.endswith('.feedback.json'):
            continue
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            _path(value['id'])
            entries.append({k: value[k] for k in ('id', 'parameters', 'seeds', 'searchedAt')})
            entries[-1]['count'] = len(value['results'])
        except (OSError, ValueError, TypeError, KeyError):
            unreadable += 1
    entries.sort(key=lambda x: x['searchedAt'], reverse=True)
    return {'groups': entries[:20], 'unreadable': unreadable}


def feedback(group_id, payload, library):
    if not isinstance(payload, dict) or type(payload.get('excluded')) is not bool:
        raise ValueError('无效的不感兴趣操作')
    with d.LOCK:
        value = load(group_id, library)
        result_id = payload.get('resultId')
        if result_id not in {hit['resultId'] for hit in value['results']}:
            raise ValueError('候选文献不存在，请重新打开当前结果')
        saved = _feedback(group_id)
        saved[result_id] = payload['excluded']
        d._atomic(_path(group_id).with_suffix('.feedback.json'), saved)
        return load(group_id, library)


def _question_search(source, seeds, plan, config):
    result = {'source': source, 'task': '围绕研究问题检索', 'warnings': [], 'hits': [], 'completed': 0}
    if not plan['query']:
        return result
    try:
        if source == 'OpenAlex':
            params = {'per-page': 30, 'select': d.OA_FIELDS}
            context = '\nContext: ' + '; '.join(s['title'] for s in seeds)
            try:
                data = d._request(source, '/works', {**params, 'search.semantic': (plan['semanticQuery'] + context)[:2000]}, config)
                method = '问题语义检索命中；尚未核对全文'
            except d.SourceError:
                data = d._request(source, '/works', {**params, 'search': plan['query']}, config)
                method = '问题关键词检索命中；尚未核对全文'
                result['warnings'].append('问题语义检索不可用，已降级为关键词检索')
            rows = (data or {}).get('results') or []
        else:
            data = d._request(source, '/graph/v1/paper/search', {'query': plan['query'], 'limit': 30, 'fields': d.FIELDS}, config)
            rows = (data or {}).get('data') or []
            method = '问题关键词检索命中；尚未核对全文'
        if data is None:
            raise d.SourceError('该来源没有返回问题检索数据')
        result['completed'] = 1
        for rank, row in enumerate(rows):
            hit = d.normalize(source, row)
            hit['relations'] = [{'kind': 'question', 'source': source, 'rank': rank + 1, 'text': method}]
            if hit['title']:
                result['hits'].append(hit)
    except d.SourceError as exc:
        result['warnings'].append(str(exc))
    return result


def _joint_recommendation(base_results, config):
    source = 'Semantic Scholar'
    result = {'source': source, 'task': '多篇联合推荐', 'warnings': [], 'hits': [], 'completed': 0}
    ids = list(dict.fromkeys(p['match']['sourceId'] for value in base_results for p in value.get('providers', [])
                            if p['source'] == source and p.get('match')))
    if len(ids) < 2:
        result['warnings'].append('至少两篇起始论文需在 Semantic Scholar 准确匹配，才能使用该来源的联合推荐')
        return result
    try:
        data = d._request(source, '/recommendations/v1/papers/', {'fields': d.FIELDS, 'limit': 30}, config, body={'positivePaperIds': ids})
        if data is None:
            raise d.SourceError('该来源没有返回联合推荐数据')
        result['completed'] = 1
        for rank, row in enumerate(data.get('recommendedPapers') or []):
            hit = d.normalize(source, row)
            hit['relations'] = [{'kind': 'similar', 'source': source, 'rank': rank + 1, 'method': 'joint',
                                 'text': f'按 {len(ids)} 篇起始论文联合推荐；不代表已证实与每篇都相关'}]
            if hit['title']:
                result['hits'].append(hit)
    except d.SourceError as exc:
        result['warnings'].append(str(exc))
    return result


def _safe(function, *args):
    try:
        return function(*args)
    except (ValueError, KeyError, TypeError, AttributeError):
        return {'source': args[0] if isinstance(args[0], str) else 'Semantic Scholar', 'task': '联合查询',
                'warnings': ['服务答复格式异常，其他结果仍可使用'], 'hits': [], 'completed': 0}


def _merge(batches, seeds, plan):
    merged = []
    tokens = list(dict.fromkeys(word.casefold() for word in re.findall(r'[A-Za-z][A-Za-z0-9-]{2,}|[\u4e00-\u9fff]{2,}', plan['query']) if word.casefold() not in STOPWORDS))[:20]
    for batch in batches:
        for hit in batch['hits']:
            if any(d.same_paper(seed, hit) for seed in seeds):
                continue
            current = next((h for h in merged if d.same_record(h, hit)), None)
            if current:
                current['relations'].extend(r for r in hit['relations'] if r not in current['relations'])
                for field in ('abstract', 'doi', 'arxiv', 'oaUrl'):
                    if not current.get(field) and hit.get(field): current[field] = hit[field]
                for field in ('isReview', 'isOpenAccess'):
                    if hit.get(field) is True: current[field] = True
                if hit['source'] not in current['sources']:current['sources'].append(hit['source'])
            else:
                merged.append({**hit, 'relations': [dict(r) for r in hit['relations']], 'sources': list(hit.get('sources') or [hit['source']])})
    for hit in merged:
        hit['relatedSeedKeys'] = sorted({r['seedKey'] for r in hit['relations'] if r.get('seedKey')})
        text = (hit['title'] + '\n' + hit.get('abstract', '')).casefold()
        hit['questionTerms'] = [term for term in tokens if (re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', text) if re.search('[a-z]', term) else term in text)]
        hit['resultId'] = d.result_id(hit)
        hit['_rank'] = (int(any(r['kind'] == 'question' for r in hit['relations'])) + int(bool(hit['questionTerms'])),
                        len(hit['relatedSeedKeys']), sum(1 / (60 + r['rank']) for r in hit['relations']))
        if hit.get('doi'):hit['url'] = 'https://doi.org/' + d.quote(hit['doi'], safe='/():;')
    merged.sort(key=lambda h:h['_rank'], reverse=True)
    for hit in merged:hit.pop('_rank')
    return merged[:60]


def search(payload, library):
    params = parameters(payload)
    seeds = validate_items(library, params)
    force = payload.get('force', False)
    if type(force) is not bool:raise ValueError('刷新参数无效')
    group_id = digest(params)
    path = _path(group_id)
    with d.LOCK:lock = LOCKS.setdefault(group_id, threading.Lock())
    with lock:
        request_jobs.check()
        previous = load(group_id, library) if path.exists() else None
        if previous and not force:return previous
        plan, config = query_plan(params), d.settings()
        with ThreadPoolExecutor(max_workers=2) as pool:
            worker = request_jobs.inherit_context(lambda seed:d.discover(seed, force=force))
            base = list(pool.map(worker, seeds))
        batches, providers, stale_keys = [], [], []
        for seed, value in zip(seeds, base):
            if value.get('stale') or value.get('preserved'):stale_keys.append(seed['key'])
            seed_hits = []
            for hit in value.get('results', []):
                seed_hits.append({**hit, 'relations': [{**r, 'seedKey':seed['key'], 'seedTitle':seed['title']} for r in hit['relations']]})
            batches.append({'hits':seed_hits})
            providers.extend({**p, 'task':'起始论文扩展', 'seedKey':seed['key'], 'seedTitle':seed['title'],
                              'cached':value.get('cached',False), 'stale':value.get('stale',False), 'candidates': value.get('candidates', [])}
                             for p in (value.get('latestAttempt') or value).get('providers', []))
        with ThreadPoolExecutor(max_workers=2) as pool:
            worker = request_jobs.inherit_context(_safe)
            futures = [pool.submit(worker,_question_search,source,seeds,plan,config) for source in d.NAMES] if plan['query'] else []
            futures.append(pool.submit(worker,_joint_recommendation,base,config))
            extra = [future.result() for future in futures]
        batches.extend(extra)
        providers.extend({k:v for k,v in batch.items() if k != 'hits'} for batch in extra)
        value = {'id':group_id,'parameters':params,'seeds':[{k:s.get(k) for k in ('key','title','doi','date','creators')} for s in seeds],
                 'plan':plan,'fingerprint':_fingerprint(seeds,plan),'results':_merge(batches,seeds,plan),'providers':providers,
                 'searchedAt':datetime.now(timezone.utc).isoformat(),'saved':False,'cached':False,'stale':bool(stale_keys),
                 'staleSeedKeys':stale_keys,'missingSeedKeys':[]}
        fresh_completed = sum(p.get('completed', 0) for p in providers if not p.get('cached'))
        if previous and ((not fresh_completed) or (not value['results'] and any(p.get('warnings') for p in providers))):
            return {**previous, 'preserved':True, 'latestAttempt':{'providers':providers}}
        if value['results'] or any(p.get('completed') for p in providers):
            with d.LOCK:
                request_jobs.check()
                d._atomic(path,value)
            value['saved'] = True
            return d.with_library(_annotate(value),library)
        return value
