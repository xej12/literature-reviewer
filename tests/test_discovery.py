"""Discovery identity, provenance, caching and HTTP integration without paid APIs."""
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import discovery as d
import request_jobs

SEED = {'key':'PAPER', 'title':'Wavefront control for exoplanet coronagraph imaging', 'doi':'10.1234/seed', 'date':'2020', 'creators':['Example Author'], 'abstract':'Control of optical wavefronts.'}


def oa(number=1, title=None, paper_doi=None, year=2020):
    return {'id': f'https://openalex.org/W{number}', 'title':title or SEED['title'],
            'doi': 'https://doi.org/' + (paper_doi or SEED['doi']), 'publication_year':year,
            'authorships':[{'author':{'display_name':'Example Author'}}], 'referenced_works':['https://openalex.org/W2'],
            'abstract_inverted_index':{'optical':[0],'wavefronts':[1]}, 'primary_location':{'landing_page_url':'https://example.org/paper','source':{'display_name':'Example Journal'}}}


def batch(source='OpenAlex', hits=None, completed=3, warnings=None):
    return {'source':source, 'match':d.normalize('OpenAlex',oa()), 'candidates':[], 'hits':hits or [], 'warnings':warnings or [], 'completed':completed}


def hit(number=2, paper_doi='10.1234/related', kind='similar', source='OpenAlex'):
    value=d.normalize('OpenAlex', oa(number, 'Related methods for precise wavefront control', paper_doi))
    value.update(source=source,relations=[{'kind':kind,'source':source,'rank':1,'text':'API relationship','seedTitle':SEED['title']}])
    return value


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        root=Path(directory.name)
        for field,value in [('CACHE_DIR',root/'cache'),('SETTINGS_PATH',root/'settings.json')]:
            patcher=patch.object(d,field,value);patcher.start();self.addCleanup(patcher.stop)

    def test_doi_conflicts_and_short_titles_never_merge(self):
        self.assertTrue(d.same_paper(SEED,{**SEED,'doi':'https://doi.org/10.1234/SEED'}))
        self.assertFalse(d.same_paper(SEED,{**SEED,'doi':'10.1234/other'}))
        self.assertTrue(d.same_paper({**SEED,'doi':''},{**SEED,'year':2020}))
        self.assertFalse(d.same_paper({**SEED,'doi':''},{**SEED,'date':'2021'}))
        self.assertFalse(d.same_paper({'title':'Introduction'},{'title':'Introduction'}))
        self.assertFalse(d.same_paper({**SEED,'doi':''},{**SEED,'creators':['Different Author']}))

    def test_duplicate_evidence_merges_but_seed_is_excluded(self):
        first,second=hit(),hit(source='Semantic Scholar',kind='citing')
        seed_hit={**d.normalize('OpenAlex',oa()),'relations':first['relations']}
        results=d.merge_results([batch(hits=[first,seed_hit]),batch('Semantic Scholar',[second])],SEED)
        self.assertEqual(len(results),1)
        self.assertEqual(set(results[0]['sources']),set(d.NAMES))
        self.assertEqual({r['kind'] for r in results[0]['relations']},{'similar','citing'})

    def test_local_library_marking_updates_even_for_cached_results(self):
        value={'results':d.merge_results([batch(hits=[hit()])],SEED)}
        self.assertFalse(d.with_library(value,[])['results'][0]['inLibrary'])
        self.assertEqual(d.with_library(value,[{'key':'LOCAL','doi':'10.1234/related'}])['results'][0]['libraryKey'],'LOCAL')
        self.assertNotIn('inLibrary',value['results'][0])

    def test_openalex_adapter_uses_real_relationships_and_labels_keyword_fallback(self):
        calls=[]
        def api(source,path,params,config):
            calls.append((path,params))
            if path.startswith('/works/'):
                return oa()
            if 'search.semantic' in params:
                raise d.SourceError('Not enabled')
            return {'results':[oa(2,'A new wavefront method','10.1234/related')]}
        with patch.object(d,'_request',side_effect=api):
            result=d._collect('OpenAlex',SEED,d.settings(),None)
        self.assertEqual(result['completed'],3)
        self.assertEqual({h['relations'][0]['kind'] for h in result['hits']},set(d.KINDS))
        self.assertIn('关键词',result['hits'][0]['relations'][0]['text'])
        self.assertTrue(any(p.get('filter','').startswith('openalex:W2') for _,p in calls))
        self.assertTrue(any(p.get('filter')=='cites:W1' for _,p in calls))

    def test_semantic_scholar_adapter_unwraps_references_citations_and_recommendations(self):
        seed={'paperId':'a'*40,'title':SEED['title'],'externalIds':{'DOI':SEED['doi']},'authors':[{'name':'Example Author'}],'year':2020}
        other={**seed,'paperId':'b'*40,'title':'Related method','externalIds':{'DOI':'10.1234/related'}}
        def api(source,path,params,config):
            if '/recommendations/' in path:return {'recommendedPapers':[other]}
            if path.endswith('/references'):return {'data':[{'citedPaper':other}]}
            if path.endswith('/citations'):return {'data':[{'citingPaper':other}]}
            return seed
        with patch.object(d,'_request',side_effect=api):
            result=d._collect('Semantic Scholar',SEED,d.settings(),None)
        self.assertEqual(result['completed'],3)
        self.assertEqual(len(result['hits']),3)
        self.assertEqual(result['hits'][0]['doi'],'10.1234/related')

    def test_ambiguous_title_is_not_expanded_until_user_confirms(self):
        paper={**SEED,'doi':'','creators':[]}
        with patch.object(d,'_request',return_value={'results':[oa(),oa(2)]}) as api:
            result=d._collect('OpenAlex',paper,d.settings(),None)
            self.assertIsNone(result['match']);self.assertEqual(len(result['candidates']),2)
            self.assertEqual(api.call_count,1)
        with patch.object(d,'_request',side_effect=lambda s,p,q,c:oa(2) if p.startswith('/works/') else {'results':[]}):
            result=d._collect('OpenAlex',paper,d.settings(),{'source':'OpenAlex','id':'https://openalex.org/W2'})
        self.assertEqual(result['match']['sourceId'],'https://openalex.org/W2')
        self.assertEqual(result['completed'],3)

    def test_cache_never_refetches_automatically_and_failed_refresh_preserves_old_results(self):
        with patch.object(d,'_safe_collect',side_effect=lambda source,*args:batch(source,[hit()] if source=='OpenAlex' else [],warnings=[])) as collect:
            initial=d.discover(SEED);self.assertTrue(initial['saved']);self.assertEqual(collect.call_count,2)
            self.assertTrue(d.discover(SEED)['cached']);self.assertEqual(collect.call_count,2)
            changed={**SEED,'abstract':'Changed material'}
            self.assertTrue(d.discover(changed)['stale']);self.assertEqual(collect.call_count,2)
        saved=d._path(SEED).read_bytes()
        with patch.object(d,'_safe_collect',side_effect=lambda source,*args:batch(source,completed=0,warnings=['Rate limited'])):
            failure=d.discover(SEED,force=True)
        self.assertTrue(failure['preserved']);self.assertEqual(len(failure['results']),1)
        self.assertEqual(d._path(SEED).read_bytes(),saved)

    def test_unresolved_seed_does_not_create_cache(self):
        with patch.object(d,'_safe_collect',side_effect=lambda source,*args:batch(source,completed=0,warnings=['Not found'])):
            result=d.discover(SEED)
        self.assertFalse(result['saved']);self.assertFalse(d._path(SEED).exists())

    def test_confirmed_match_is_retained_for_refresh_and_other_provider_is_not_mixed(self):
        selection={'source':'OpenAlex','id':'https://openalex.org/W2'}
        with patch.object(d,'_request') as api:
            other=d._collect('Semantic Scholar',SEED,d.settings(),selection)
            self.assertEqual(other['completed'],0);api.assert_not_called()
        selections=[]
        def collect(source,item,config,selected):
            selections.append(selected)
            return batch(source,[hit()] if source=='OpenAlex' else [])
        with patch.object(d,'_safe_collect',side_effect=collect):
            d.discover(SEED,selected=selection);d.discover(SEED,force=True)
        self.assertEqual(selections,[selection]*4)

    def test_parallel_first_requests_share_one_search_and_corrupt_cache_is_preserved(self):
        calls=[]
        def collect(source,*args):
            calls.append(source);time.sleep(.02)
            return batch(source,[hit()])
        with patch.object(d,'_safe_collect',side_effect=collect):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(lambda _:d.discover(SEED),range(2)))
        self.assertTrue(all(r['saved'] for r in results));self.assertEqual(len(calls),2)
        path=d._path(SEED);path.write_text('{broken',encoding='utf-8')
        with patch.object(d,'_safe_collect',side_effect=AssertionError('Must preserve corrupt cache')):
            with self.assertRaises(ValueError):d.discover(SEED,force=True)
        self.assertEqual(path.read_text(encoding='utf-8'),'{broken')

    def test_settings_keep_blank_keys_clear_explicitly_and_never_expose_secrets(self):
        public=d.save_settings({'openalexKey':'secret-key','semanticScholarKey':'s2-secret'})
        self.assertTrue(public['openalexConfigured']);self.assertNotIn('secret',json.dumps(public))
        d.save_settings({'openalexKey':''});self.assertEqual(d.settings()['openalexKey'],'secret-key')
        d.save_settings({'clearOpenalexKey':True});self.assertEqual(d.settings()['openalexKey'],'')
        for value in ['bad\nheader',23,'x'*501]:
            with self.assertRaises(ValueError):d.save_settings({'openalexKey':value})

    def test_http_error_does_not_leak_key_or_url(self):
        error=urllib.error.HTTPError('https://example.org/?api_key=SECRET',429,'SECRET',{},None)
        with patch.object(request_jobs,'urlopen',side_effect=error):
            with self.assertRaises(d.SourceError) as raised:d._request('OpenAlex','/works',{}, {'openalexKey':'SECRET'})
        self.assertNotIn('SECRET',str(raised.exception));self.assertIn('限流',str(raised.exception))

    def test_cancel_worker_stops_followup_queries_and_prevents_cache_write(self):
        identifier='c'*32;started=threading.Event()
        def worker(source,*args):
            started.set()
            while True:
                request_jobs.check();time.sleep(.01)
        with patch.object(d,'_safe_collect',side_effect=worker):
            def search():
                with request_jobs.scope(identifier):return d.discover(SEED)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(search);self.assertTrue(started.wait(3));request_jobs.cancel(identifier)
                with self.assertRaises(request_jobs.Cancelled):future.result(timeout=3)
        self.assertFalse(d._path(SEED).exists())

    def test_unsafe_links_and_invalid_selection_are_rejected(self):
        for value in ['javascript:alert(1)','file:///secret','https://name:password@example.org','https://example.org/\nsecret']:
            self.assertEqual(d.safe_url(value),'')
        with self.assertRaises(ValueError):d.discover(SEED,selected={'source':'OpenAlex','id':'../../api/model'})
        with self.assertRaises(ValueError):d.cached({**SEED,'key':'../secret'})

    def test_http_route_reads_cache_marks_library_and_never_calls_model(self):
        spec=importlib.util.spec_from_file_location('reviewer_discovery_http',Path(__file__).resolve().parents[1]/'scripts/server.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        store=Mock();store.item.return_value=SEED;store._all_items.return_value=[{'key':'KNOWN','doi':'10.1234/related'}]
        with patch.object(module,'STORE',store),patch.object(module,'model_config',side_effect=AssertionError('No models')),patch.object(d,'_safe_collect',side_effect=lambda source,*args:batch(source,[hit()])) as collect:
            server=ThreadingHTTPServer(('127.0.0.1',0),module.Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def request(path,payload=None):
                req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,data=json.dumps(payload).encode() if payload is not None else None,headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(req) as response:return json.load(response)
            try:
                self.assertFalse(request('/api/items/PAPER/discovery')['saved']);collect.assert_not_called()
                self.assertTrue(request('/api/items/PAPER/discovery',{})['results'][0]['inLibrary'])
                self.assertTrue(request('/api/items/PAPER/discovery')['cached']);self.assertEqual(collect.call_count,2)
                self.assertTrue(request('/api/discovery/settings',{'openalexKey':'test-secret'})['openalexConfigured'])
                self.assertNotIn('test-secret',json.dumps(request('/api/discovery/settings')))
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
