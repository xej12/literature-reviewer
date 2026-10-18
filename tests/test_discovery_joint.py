"""Joint discovery contracts: identity, provenance, persistence, cancellation, HTTP."""
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
from unittest.mock import patch, Mock
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import discovery as d
import discovery_joint as j
import request_jobs

SEEDS=[{'key':f'PAPER{n}','title':f'Wavefront estimation research number {n}', 'doi':f'10.1234/seed{n}', 'date':'2020','creators':['A Author']} for n in (1,2)]
PARAMS={'itemKeys':['PAPER1','PAPER2'],'question':'How to improve broadband coronagraph imaging?','keywords':''}

def candidate(number=3,source='OpenAlex',kind='similar'):
    return {'source':source,'sourceId':f'W{number}' if source=='OpenAlex' else str(number)*40,
            'title':f'Broadband coronagraph wavefront method {number}', 'doi':f'10.1234/result{number}', 'arxiv':'',
            'year':2021,'creators':['A Author'],'publicationTitle':'Optics','abstract':'Broadband wavefront control.',
            'url':f'https://doi.org/10.1234/result{number}','oaUrl':'','isOpenAccess':False,'isReview':None,
            'relations':[{'kind':kind,'source':source,'rank':1,'text':'API evidence'}]}

def base(seed,force=False):
    return {'saved':True,'cached':not force,'results':[candidate()], 'providers':[
        {'source':'Semantic Scholar','match':{'sourceId':seed['key'][-1]*40},'completed':3,'warnings':[]}], 'candidates':[]}

class JointTests(unittest.TestCase):
    def setUp(self):
        root=tempfile.TemporaryDirectory();self.addCleanup(root.cleanup)
        self.root=Path(root.name)
        for obj,field,value in [(d,'CACHE_DIR',self.root/'cache'),(d,'SETTINGS_PATH',self.root/'settings.json'),
                                 (j.translation,'glossary',lambda:{'entries':[{'term':'coronagraph','translation':'日冕仪'}]}),
                                 (j.reading_priority,'profile',lambda:{'topics':'波前控制 | wavefront control'})]:
            p=patch.object(obj,field,value);p.start();self.addCleanup(p.stop)

    def search(self,**kwargs):
        with patch.object(d,'discover',side_effect=base),patch.object(d,'_request',return_value={'results':[],'data':[],'recommendedPapers':[]}):
            return j.search({**PARAMS,**kwargs},SEEDS)

    def test_validation_and_identity(self):
        for keys in [[],['PAPER1'],['PAPER1']*2,['../bad','PAPER1'],list('ABCDEF')]:
            with self.assertRaises(ValueError):j.parameters({**PARAMS,'itemKeys':keys})
        with self.assertRaises(ValueError):j.validate_items([SEEDS[0],{**SEEDS[1],'doi':SEEDS[0]['doi']}],j.parameters(PARAMS))
        with self.assertRaises(ValueError):j.validate_items([SEEDS[0],{**SEEDS[1],'doi':'','url':'https://doi.org/'+SEEDS[0]['doi']}],j.parameters(PARAMS))
        self.assertTrue(d.same_paper({'url':'https://arxiv.org/pdf/1234.56789v2'},{'arxiv':'1234.56789'}))
        with self.assertRaises(FileNotFoundError):j.validate_items(SEEDS[:1],j.parameters(PARAMS))
        a=j.parameters(PARAMS);b=j.parameters({**PARAMS,'itemKeys':list(reversed(PARAMS['itemKeys']))})
        self.assertEqual(j.digest(a),j.digest(b))
        self.assertNotEqual(j.digest(a),j.digest(j.parameters({**PARAMS,'question':'another question'})))
        with self.assertRaises(ValueError):j._path('../../x')

    def test_chinese_uses_professional_glossary_and_explicit_keywords_override(self):
        plan=j.query_plan({'question':'日冕仪的波前控制有什么进展？','keywords':''})
        self.assertIn('coronagraph',plan['query']);self.assertIn('wavefront control',plan['query'])
        self.assertEqual(j.query_plan({'question':'日冕仪','keywords':'specific method'})['query'],'specific method')
        self.assertTrue(j.query_plan({'question':'一个未收录的中文主题','keywords':''})['notice'])

    def test_question_is_sent_and_semantic_fallback_is_labeled(self):
        calls=[]
        def api(source,path,params,config,body=None):
            calls.append(params)
            if 'search.semantic' in params:raise d.SourceError('unavailable')
            return {'results':[{'id':'https://openalex.org/W3','title':'Broadband research','doi':'10.1234/result3','type':'review','open_access':{'is_oa':True}}]}
        plan=j.query_plan(j.parameters(PARAMS))
        with patch.object(d,'_request',side_effect=api):value=j._question_search('OpenAlex',SEEDS,plan,{})
        self.assertIn(PARAMS['question'],calls[0]['search.semantic'])
        self.assertEqual(calls[1]['search'],plan['query'])
        self.assertIn('关键词',value['hits'][0]['relations'][0]['text']);self.assertTrue(value['warnings'])
        self.assertTrue(value['hits'][0]['isReview']);self.assertTrue(value['hits'][0]['isOpenAccess'])

    def test_multiple_positive_papers_use_post_json_and_not_fake_coverage(self):
        bases=[base(s) for s in SEEDS]
        with patch.object(d,'_request',return_value={'recommendedPapers':[{'paperId':'3'*40,'title':'Broadband coronagraph','externalIds':{'DOI':'10.1234/result3'}}]}) as api:
            value=j._joint_recommendation(bases,{})
        self.assertEqual(api.call_args.kwargs['body'],{'positivePaperIds':['1'*40,'2'*40]})
        merged=j._merge([value],SEEDS,{'query':'coronagraph'})
        self.assertEqual(merged[0]['relatedSeedKeys'],[])
        self.assertEqual(merged[0]['questionTerms'],['coronagraph'])

    def test_request_body_really_uses_post_without_exposing_keys(self):
        response=Mock();response.read.return_value=b'{"recommendedPapers":[]}'
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        with patch.object(request_jobs,'urlopen',return_value=response) as call:
            d._request('Semantic Scholar','/recommendations/v1/papers/',{}, {'semanticScholarKey':'private'},body={'positivePaperIds':['1','2']})
        req=call.call_args.args[0]
        self.assertEqual(req.get_method(),'POST');self.assertEqual(json.loads(req.data),{'positivePaperIds':['1','2']})

    def test_merge_excludes_all_seeds_and_counts_distinct_evidence(self):
        hits=[]
        for seed in SEEDS:
            h=candidate();h['relations'][0].update(seedKey=seed['key'],seedTitle=seed['title']);hits.append(h)
            hits.append({**candidate(),**seed})
        other=candidate(source='Semantic Scholar');other.update(isReview=True,isOpenAccess=True)
        merged=j._merge([{'hits':hits+[other]}],SEEDS,{'query':'coronagraph'})
        self.assertEqual(len(merged),1);self.assertEqual(len(merged[0]['relatedSeedKeys']),2)
        self.assertEqual(len(merged[0]['sources']),2);self.assertTrue(merged[0]['isReview']);self.assertTrue(merged[0]['isOpenAccess'])
        conflict=candidate();conflict['doi']='10.1234/different'
        self.assertEqual(len(j._merge([{'hits':[candidate(),conflict]}],SEEDS,{'query':''})),2)
        self.assertEqual(j._merge([{'hits':[{**candidate(), 'doi':SEEDS[0]['doi']}]}],[{**SEEDS[0],'doi':'','url':'https://doi.org/'+SEEDS[0]['doi']},SEEDS[1]],{'query':''}),[])

    def test_cache_history_feedback_reopen_without_any_network(self):
        value=self.search();self.assertTrue(value['saved']);self.assertEqual(len(value['results'][0]['relatedSeedKeys']),2)
        with patch.object(d,'discover',side_effect=AssertionError('No network')),patch.object(d,'_request',side_effect=AssertionError('No network')):
            again=j.search({**PARAMS,'itemKeys':list(reversed(PARAMS['itemKeys']))},SEEDS)
            self.assertEqual(again['searchedAt'],value['searchedAt']);self.assertTrue(again['cached'])
            self.assertEqual(len(j.history()['groups']),1)
            result_id=value['results'][0]['resultId']
            self.assertTrue(j.feedback(value['id'],{'resultId':result_id,'excluded':True},SEEDS)['results'][0]['excluded'])
            self.assertFalse(j.feedback(value['id'],{'resultId':result_id,'excluded':False},SEEDS)['results'][0]['excluded'])
            self.assertEqual(len(j.history()['groups']),1)
            self.assertTrue(j.load(value['id'],SEEDS+[{'key':'KNOWN','doi':'10.1234/result3'}])['results'][0]['inLibrary'])
        with self.assertRaises(ValueError):j.feedback(value['id'],{'resultId':'missing','excluded':True},SEEDS)
        self.assertTrue(j.load(value['id'],[{**SEEDS[0],'title':'Changed'},SEEDS[1]])['stale'])
        self.assertTrue(j.load(value['id'],SEEDS[:1])['missingSeedKeys'])

    def test_stale_seed_and_failed_refresh_preserve_original_timestamp(self):
        value=self.search()
        failed={**base(SEEDS[0]),'cached':True,'preserved':True,'latestAttempt':{'providers':[{'source':'OpenAlex','completed':0,'warnings':['failed']}]}}
        with patch.object(d,'discover',return_value=failed),patch.object(d,'_request',side_effect=d.SourceError('failed')):
            result=j.search({**PARAMS,'force':True},SEEDS)
        self.assertTrue(result['preserved']);self.assertEqual(result['searchedAt'],value['searchedAt'])
        self.assertEqual(j.load(value['id'],SEEDS)['searchedAt'],value['searchedAt'])
        # A newly created group must retain its stale-seed warning after reopening.
        with patch.object(d,'discover',return_value={**base(SEEDS[0]),'stale':True}),patch.object(d,'_request',return_value={'results':[],'data':[],'recommendedPapers':[]}):
            result=j.search({**PARAMS,'question':'changed question'},SEEDS)
        self.assertTrue(j.load(result['id'],SEEDS)['stale'])

    def test_cancelled_work_cannot_save_group(self):
        started=threading.Event();identifier='e'*32
        def slow(*args,**kwargs):
            started.set()
            while True:request_jobs.check();time.sleep(.01)
        def run():
            with request_jobs.scope(identifier):return j.search(PARAMS,SEEDS)
        with patch.object(d,'discover',side_effect=slow):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(run);self.assertTrue(started.wait(3));request_jobs.cancel(identifier)
                with self.assertRaises(request_jobs.Cancelled):future.result(timeout=3)
        self.assertEqual(j.history()['groups'],[])

    def test_corrupt_group_is_preserved(self):
        value=self.search();path=j._path(value['id']);path.write_text('{bad',encoding='utf-8')
        with self.assertRaises(ValueError):j.search({**PARAMS,'force':True},SEEDS)
        self.assertEqual(path.read_text(),'{bad');self.assertEqual(j.history()['unreadable'],1)

    def test_http_joint_routes_and_picker_do_not_call_model(self):
        spec=importlib.util.spec_from_file_location('joint_test_server',Path(__file__).resolve().parents[1]/'scripts/server.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        store=Mock();store._all_items.return_value=SEEDS
        with patch.object(module,'STORE',store),patch.object(module,'model_config',side_effect=AssertionError('No model')),patch.object(d,'discover',side_effect=base),patch.object(d,'_request',return_value={'results':[],'data':[],'recommendedPapers':[]}):
            server=ThreadingHTTPServer(('127.0.0.1',0),module.Handler);t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
            def req(path,payload=None):
                request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,data=json.dumps(payload).encode() if payload is not None else None)
                with urllib.request.urlopen(request) as r:return json.load(r)
            try:
                self.assertEqual(req('/api/discovery/library')['total'],2)
                value=req('/api/discovery/groups',PARAMS);self.assertTrue(value['saved'])
                self.assertEqual(len(req('/api/discovery/groups')['groups']),1)
                self.assertTrue(req('/api/discovery/groups/'+value['id'])['cached'])
                self.assertTrue(req('/api/discovery/groups/'+value['id']+'/feedback',{'resultId':value['results'][0]['resultId'],'excluded':True})['results'][0]['excluded'])
            finally:server.shutdown();server.server_close();t.join()

if __name__=='__main__':unittest.main()
