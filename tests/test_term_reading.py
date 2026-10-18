"""Per-term lessons: evidence selection, independent caches and safe paid actions."""
from concurrent.futures import ThreadPoolExecutor
import http.client
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('reviewer_term_lessons', Path(__file__).resolve().parents[1] / 'scripts/server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
terms = server.term_reading
deep = server.deep_reading


class TermReadingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.item = {'key':'TEST','title':'Coronagraph design','attachments':[{'key':'PDF','exists':True,'contentType':'application/pdf'}]}
        pages = ['Physical methods and experimental conditions. ' * 25 for _ in range(19)]
        pages[17] = 'The coronagraph suppresses on-axis starlight. ' * 25
        self.corpus = deep.build_corpus(self.item, 'PDF', pages)
        self.store = Mock();self.store.item.return_value=self.item;self.store.deep_corpus.return_value=(self.item,self.corpus)
        self.config = {'configured':True,'model':'deepseek-flash','baseUrl':'https://api.deepseek.com','apiKey':'fake-only'}
        patches = [patch.object(server,'STORE',self.store),patch.object(server,'model_config',return_value=self.config),
            patch.object(server,'TERM_READING_DIR',self.directory/'terms'),patch.object(server,'DEEP_READING_DIR',self.directory/'deep'),
            patch.object(server,'ANALYSIS_DIR',self.directory/'analysis'),patch.object(server.translation,'GLOSSARY_PATH',self.directory/'glossary.json')]
        for patcher in patches:patcher.start();self.addCleanup(patcher.stop)

    def response(self, content=None, finish='stop'):
        if content is None:
            content=json.dumps({'intro':'Understand the optical mechanism.', 'blocks':[
                {'title':'本文机制','body':'Explains the physical mechanism.','basis':'paper','sourceIds':['P0018C001']},
                {'title':'教学例子','body':'An illustrative example, not a paper result. $I=|E|^2$','basis':'background','sourceIds':[]} ]})
        return io.BytesIO(json.dumps({'choices':[{'finish_reason':finish,'message':{'content':content}}]}).encode())

    def test_late_term_mentions_take_priority_under_context_limit(self):
        selected,coverage=terms.select_context(self.corpus,'coronagraph',max_chars=4500)
        self.assertIn('P0018C001',[c['id'] for c in selected])
        self.assertEqual(coverage['matchedPages'],[18])
        self.assertEqual(coverage['includedMatchedPages'],[18])
        self.assertTrue(coverage['partial'])
        self.assertLessEqual(sum(len(c['text'])+len(c['id'])+30 for c in selected),4500)
        self.assertFalse(terms.select_context(self.corpus,'nonexistent concept')[1]['termFound'])
        self.assertTrue(terms.select_context(self.corpus,'日冕仪')[1]['termFound'])

    def test_teaching_prompt_is_specific_and_source_types_are_explicit(self):
        selected,coverage=terms.select_context(self.corpus,'coronagraph')
        prompt=terms.prompt(self.item,'coronagraph',selected,coverage)
        for expected in ('工作机制','教学例子','易混淆','自检','日冕仪','sourceIds','P0018C001','paper','background','inference'):
            self.assertIn(expected,prompt)
        self.assertNotIn('本次只生成章节：阅读导览',prompt)

    def test_term_cache_is_separate_and_concurrent_reopens_generate_once(self):
        with patch.object(server.urllib.request,'urlopen',side_effect=lambda *a,**k:self.response()) as model:
            with ThreadPoolExecutor(max_workers=2) as workers:
                results=list(workers.map(lambda _:server.generate_term_lesson('TEST','coronagraph'),range(2)))
            self.assertEqual(model.call_count,1)
            self.assertTrue(any(r['cached'] for r in results))
            identifier=terms.term_id('coronagraph')
            self.assertEqual(results[0]['reading']['sections'][identifier]['term'],'coronagraph')
            self.assertEqual(results[0]['reading']['sections'][identifier]['blocks'][0]['sources'][0]['page'],18)
            self.assertFalse(deep.has_reading(server.DEEP_READING_DIR,'TEST'))
            state=server.term_reading_state('TEST')
            self.assertEqual(state['chapters'][0]['term'],'coronagraph')
            self.assertEqual(model.call_count,1)
            body=json.loads(model.call_args.args[0].data)
            self.assertNotIn('max_tokens',body)
            self.assertEqual(model.call_args.kwargs['timeout'],600)
            server.generate_term_lesson('TEST','wavefront')
            self.assertEqual(model.call_count,2)
            self.assertEqual(len(server.term_reading_state('TEST')['reading']['sections']),2)

    def test_failed_retry_is_saved_and_free_repair_preserves_success(self):
        identifier=terms.term_id('coronagraph')
        with patch.object(server.urllib.request,'urlopen',side_effect=lambda *a,**k:self.response()) as model:
            server.generate_term_lesson('TEST','coronagraph')
            model.side_effect=lambda *a,**k:self.response('{"blocks":[',finish='length')
            pending=server.generate_term_lesson('TEST','coronagraph',force=True)
            self.assertTrue(pending['pending'])
            self.assertIn(identifier,pending['reading']['sections'])
            self.assertEqual(pending['reading']['drafts'][identifier]['content'],'{"blocks":[')
            self.assertTrue(server.generate_term_lesson('TEST','coronagraph',repair_only=True)['pending'])
            self.assertEqual(model.call_count,2)
            model.side_effect=lambda *a,**k:self.response()
            repaired=server.generate_term_lesson('TEST','coronagraph',force=True)
            self.assertEqual(len(repaired['reading']['history'][identifier]),1)
            self.assertNotIn(identifier,repaired['reading']['drafts'])
            self.assertEqual(model.call_count,3)
            self.assertTrue(server.generate_term_lesson('TEST','unknown',repair_only=True)['noDraft'])
            self.assertEqual(model.call_count,3)

    def test_glossary_and_pdf_changes_keep_old_lessons_without_reusing_them(self):
        with patch.object(server.urllib.request,'urlopen',side_effect=lambda *a,**k:self.response()) as model:
            first=server.generate_term_lesson('TEST','coronagraph')
            server.translation.save_term({'term':'coronagraph','translation':'日冕仪','note':'追加领域说明'})
            changed=server.term_reading_state('TEST','coronagraph')
            self.assertEqual(changed['reading']['sections'],{})
            self.assertEqual(changed['versions'][0]['fingerprint'],first['reading']['fingerprint'])
            self.assertEqual(model.call_count,1)
            server.generate_term_lesson('TEST','coronagraph')
            changed_pdf={**self.corpus,'fingerprint':'changed-pdf'}
            self.store.deep_corpus.return_value=(self.item,changed_pdf)
            self.assertEqual(server.term_reading_state('TEST')['reading']['sections'],{})
            self.assertEqual(len(server.term_reading_state('TEST')['versions']),2)
            self.assertEqual(model.call_count,2)

    def test_missing_pdf_retains_saved_view_and_prevents_generation(self):
        with patch.object(server.urllib.request,'urlopen',side_effect=lambda *a,**k:self.response()) as model:
            server.generate_term_lesson('TEST','coronagraph')
            self.store.deep_corpus.side_effect=ValueError('PDF 可提取正文不足')
            state=server.term_reading_state('TEST')
            self.assertIsNone(state['source'])
            self.assertIn('正文不足',state['sourceError'])
            self.assertEqual(len(state['versions']),1)
            with self.assertRaises(ValueError):server.generate_term_lesson('TEST','coronagraph')
            self.assertEqual(model.call_count,1)

    def test_http_open_is_free_and_repair_never_calls_model(self):
        http_server=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        threading.Thread(target=http_server.serve_forever,daemon=True).start()
        self.addCleanup(http_server.server_close);self.addCleanup(http_server.shutdown)
        def request(method,suffix='',payload=None):
            connection=http.client.HTTPConnection('127.0.0.1',http_server.server_port)
            connection.request(method,'/api/items/TEST/term-reading'+suffix,json.dumps(payload) if payload is not None else None,{'Content-Type':'application/json'})
            response=connection.getresponse();value=json.loads(response.read());connection.close()
            return response.status,value
        with patch.object(server.urllib.request,'urlopen',side_effect=lambda *a,**k:self.response()) as model:
            status,value=request('GET','?term=coronagraph')
            self.assertEqual(status,200);self.assertTrue(value['source']['termFound']);model.assert_not_called()
            status,value=request('POST',payload={'term':'coronagraph','repairOnly':True})
            self.assertTrue(value['noDraft']);model.assert_not_called()
            status,_=request('POST',payload={'term':'coronagraph'})
            self.assertEqual(status,200);self.assertEqual(model.call_count,1)
            status,value=request('POST',payload={'term':'coronagraph'})
            self.assertTrue(value['cached']);self.assertEqual(model.call_count,1)
            status,_=request('POST',payload={'term':'x'*151})
            self.assertEqual(status,400);self.assertEqual(model.call_count,1)


if __name__=='__main__':unittest.main()
