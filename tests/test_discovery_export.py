"""Selection boundaries and cached bibliography downloads; no scholarly/model requests."""
from http.server import ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import urllib.request
import urllib.error

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import discovery as d
import discovery_joint as j
import discovery_export as e

SEED={'key':'PAPER','title':'A wavefront estimation paper','doi':'10.1234/seed','date':'2020','creators':['A Author']}
OTHER={**SEED,'key':'SECOND','doi':'10.1234/second','title':'Another seed paper'}

def hit(n=1):
    return {'title':f'日冕仪 coronagraph study {n}', 'source':'OpenAlex','sourceId':f'https://openalex.org/W{n}',
            'doi':f'10.1234/paper{n}','arxiv':'','year':2024,'creators':['张三','A. Researcher','Team and Partners'],
            'publicationTitle':'Optics Letters','url':f'https://doi.org/10.1234/paper{n}',
            'oaUrl':f'https://example.org/open/{n}.pdf','abstract':'A % gain with $x_1$ & {data}.',
            'sources':['OpenAlex','Semantic Scholar'],'relations':[{'source':'OpenAlex','text':'起始论文的参考文献','seedTitle':SEED['title']}],
            'resultId':d.result_id({'doi':f'10.1234/paper{n}'})}

class ExportTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.directory=Path(temporary.name)
        for obj,field,value in [(d,'CACHE_DIR',self.directory/'cache'),(j,'query_plan',lambda _: {'query':'wavefront','semanticQuery':'wavefront','expandedTerms':[],'notice':''})]:
            p=patch.object(obj,field,value);p.start();self.addCleanup(p.stop)
        self.results=[hit(1),hit(2)]
        self.value={'saved':True,'seed':SEED,'searchedAt':'2026-10-18T00:00:00+00:00','fingerprint':d.fingerprint(SEED),'results':self.results}
        d._atomic(d._path(SEED),self.value)
        self.no_remote=patch.object(d,'_request',side_effect=AssertionError('No academic API requests'))
        self.no_remote.start();self.addCleanup(self.no_remote.stop)

    def payload(self,**kwargs):
        return {'itemKey':'PAPER','resultIds':[self.results[0]['resultId']],'format':'ris',**kwargs}

    def test_selected_subset_and_saved_order_no_refresh_or_mutation(self):
        before=d._path(SEED).read_bytes()
        with patch.object(d,'discover',side_effect=AssertionError('No refresh')):
            result=e.export(self.payload(),[SEED])
            self.assertEqual(result['count'],1)
            self.assertIn(self.results[0]['title'],result['content']);self.assertNotIn(self.results[1]['title'],result['content'])
            result=e.export(self.payload(resultIds=[h['resultId'] for h in reversed(self.results)]),[SEED])
            self.assertLess(result['content'].index(self.results[0]['title']),result['content'].index(self.results[1]['title']))
        self.assertEqual(d._path(SEED).read_bytes(),before)

    def test_invalid_or_stale_selection_never_silently_exports_other_papers(self):
        for change in [{'format':'html'},{'format':[]},{'resultIds':[]},{'resultIds':['../bad']},{'resultIds':['f'*64]},
                       {'resultIds':[self.results[0]['resultId']]*2},{'itemKey':'../bad'},{'groupId':'a'*64}]:
            with self.assertRaises(ValueError):e.export(self.payload(**change),[SEED])
        with self.assertRaises(FileNotFoundError):e.export(self.payload(),[OTHER])
        d._path(SEED).unlink()
        with self.assertRaises(ValueError):e.export(self.payload(),[SEED])

    def test_ris_full_authors_chinese_primary_link_and_no_invented_year(self):
        result=e.export(self.payload(),[SEED])
        text=result['content']
        self.assertTrue(result['filename'].endswith('.ris'));self.assertEqual(text.count('TY  - GEN'),1)
        self.assertEqual(text.count('AU  - '),3);self.assertIn('AU  - Team and Partners\n',text)
        self.assertIn('PY  - 2024\n',text);self.assertIn('T2  - Optics Letters\n',text)
        self.assertEqual(text.count('UR  - '),1);self.assertIn('N1  - Open access:',text)
        missing={**hit(),'year':None,'creators':[],'doi':''}
        text=e.ris([missing]);self.assertNotIn('PY  - ',text);self.assertNotIn('DO  - ',text)

    def test_field_newlines_cannot_create_fake_ris_records(self):
        malicious={**hit(),'title':'An original title\nER  - \nTY  - JOUR','abstract':'text\r\nAU  - injected'}
        text=e.ris([malicious])
        self.assertEqual(sum(line.startswith('TY  - ') for line in text.splitlines()),1)
        self.assertEqual(sum(line.startswith('ER  - ') for line in text.splitlines()),1)
        self.assertEqual(sum(line.startswith('AU  - ') for line in text.splitlines()),3)

    def test_bibtex_preserves_title_case_literal_names_and_escapes_special_symbols(self):
        text=e.bibtex([{**hit(),'title':r'100% {SPHERE} & $x_1$ #a ~b ^c \input{file}'}])
        self.assertIn('title = {{100\\% \\{SPHERE\\} \\& \\$x\\_1\\$',text)
        self.assertIn('\\textbackslash{}input\\{file\\}',text)
        self.assertIn('author = {{张三} and {A. Researcher} and {Team and Partners}}',text)
        self.assertTrue(text.startswith('@misc{lr_'));self.assertNotIn('@article',text)
        self.assertEqual(e.bibtex([hit()]),e.bibtex([hit()]))
        self.assertIn('url = {https://example.org/a_b?x=1&y=2}',e.bibtex([{**hit(),'url':'https://example.org/a_b?x=1&y=2'}]))

    def test_markdown_contains_context_provenance_and_safe_notes_template(self):
        value={**self.value,'parameters':{'question':'<script>bad</script> [link](evil)','keywords':'wavefront'},'stale':True}
        text=e.markdown([{**hit(),'title':'<img onerror=x> [bad](javascript:alert(1))', 'oaUrl':'javascript:alert(1)'}],value)
        self.assertIn('研究问题：',text);self.assertIn('起始论文：',text);self.assertIn('检索时间：',text)
        self.assertIn('关联依据：',text);self.assertIn('我的阅读笔记',text);self.assertIn('旧资料',text)
        self.assertNotIn('<script>',text);self.assertNotIn('<img',text);self.assertNotIn('[bad](',text)
        self.assertIn('[DOI / 原文](<https://doi.org/10.1234/paper1>)',text)
        self.assertNotIn('[开放获取]',text)

    def test_joint_saved_feedback_is_respected_without_network(self):
        params=j.parameters({'itemKeys':['PAPER','SECOND'],'question':'Research question'})
        group_id=j.digest(params);path=j._path(group_id)
        value={**self.value,'id':group_id,'parameters':params,'seeds':[SEED,OTHER],
               'fingerprint':j._fingerprint([SEED,OTHER],j.query_plan(params))}
        d._atomic(path,value)
        payload=self.payload(itemKey=None,groupId=group_id,format='markdown')
        self.assertEqual(e.export(payload,[SEED,OTHER])['count'],1)
        j.feedback(group_id,{'resultId':self.results[0]['resultId'],'excluded':True},[SEED,OTHER])
        with self.assertRaises(ValueError):e.export(payload,[SEED,OTHER])
        j.feedback(group_id,{'resultId':self.results[0]['resultId'],'excluded':False},[SEED,OTHER])
        self.assertEqual(e.export(payload,[SEED,OTHER])['count'],1)

    def test_old_cache_without_result_ids_is_supported_and_id_stays_compatible(self):
        for h in self.value['results']:h.pop('resultId')
        d._atomic(d._path(SEED),self.value)
        available=d.with_library(d.cached(SEED),[])['results']
        self.assertEqual(available[0]['resultId'],j.digest({'doi':self.results[0]['doi']}))
        self.assertEqual(e.export({'itemKey':'PAPER','format':'bibtex','resultIds':[available[0]['resultId']]},[SEED])['count'],1)

    def test_http_export_no_model_no_secrets_and_errors_are_json(self):
        spec=importlib.util.spec_from_file_location('export_test_server',Path(__file__).resolve().parents[1]/'scripts/server.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        store=Mock();store._all_items.return_value=[SEED]
        with patch.object(module,'STORE',store),patch.object(module,'model_config',side_effect=AssertionError('No model')):
            server=ThreadingHTTPServer(('127.0.0.1',0),module.Handler);t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
            def request(payload):
                req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/discovery/export',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
                return urllib.request.urlopen(req)
            try:
                for format_name in e.FORMATS:
                    with request(self.payload(format=format_name)) as response:
                        value=json.load(response);self.assertEqual(value['count'],1);self.assertNotIn('apiKey',json.dumps(value))
                with self.assertRaises(urllib.error.HTTPError) as raised:request(self.payload(resultIds=['f'*64]))
                self.assertEqual(raised.exception.code,400);self.assertIn('error',json.load(raised.exception))
            finally:server.shutdown();server.server_close();t.join()

if __name__=='__main__':unittest.main()
