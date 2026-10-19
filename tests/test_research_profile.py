"""Research goals belong to the reader; metadata suggestions never save them."""
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import reading_priority as rp
import research_suggestions as suggestions
import request_jobs
import server


class ResearchProfileTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for name, value in (('PROFILE_PATH', self.root / 'research.json'), ('CACHE_DIR', self.root / 'priority')):
            p = patch.object(rp, name, value)
            p.start(); self.addCleanup(p.stop)

    def test_new_install_and_invalid_profile_have_no_assumed_discipline(self):
        for contents in (None, '{}', 'null', '{broken', '{"goal":123,"topics":[]}'):
            if contents is not None:
                rp.PROFILE_PATH.write_text(contents, encoding='utf-8')
            result = rp.profile()
            self.assertEqual((result['goal'], result['topics'], result['configured']), ('', '', False))
        self.assertFalse(rp.CACHE_DIR.exists())

    def test_saved_goal_and_cache_version_preserved_and_keywords_optional(self):
        for goal, topics in [('生物医学中的药物递送', 'drug delivery'), ('日冕仪中的波前控制', 'coronagraph')]:
            original = {'goal': goal, 'topics': topics}
            rp.PROFILE_PATH.write_text(json.dumps(original), encoding='utf-8')
            result = rp.profile()
            self.assertEqual(result['version'], rp.digest(original))
            self.assertTrue(result['configured'])
            store = server.ZoteroStore.__new__(server.ZoteroStore)
            store._all_items = Mock(return_value=[{'key': 'NEW', 'title': 'A completely different subject'}])
            store._visible_collections = Mock(return_value=[])
            store.version = 'test'
            with patch.object(server, 'load_analysis', return_value={}):
                store.library()
            self.assertEqual(rp.profile(), result)
        self.assertTrue(rp.save_profile({'goal': '我的新课题'})['configured'])
        self.assertEqual(rp.profile()['topics'], '')
        for invalid in ({'goal': ''}, {'goal': ['bad']}, {'goal': 'valid', 'topics': None}):
            with self.assertRaises(ValueError): rp.save_profile(invalid)

    def test_missing_goal_rejected_before_model_configuration_or_call(self):
        with patch.object(server, 'model_config') as config:
            with self.assertRaises(ValueError): server.generate_priority({}, {}, rp.profile())
            config.assert_not_called()

    def test_suggestion_uses_only_selected_metadata_and_never_saves(self):
        store = Mock()
        store.item.side_effect = lambda key: {'key': key, 'title': 'Genomics', 'abstract': 'RNA sequencing',
                                             'privateNote': 'do not send', 'pdfText': 'do not send PDF'}
        papers = suggestions.selected_papers(store, {'keys': ['BIO1', 'BIO2']})
        store.analysis_context.assert_not_called()
        draft = {'goal': '研究 RNA 测序方法', 'topics': 'RNA测序 | RNA sequencing', 'reason': '仅依据两篇摘要，尚不清楚实验需求。'}
        response = {'choices': [{'message': {'content': '```json\n' + json.dumps(draft) + '\n```'}, 'finish_reason': 'stop'}]}
        config = {'configured': True, 'baseUrl': 'https://example.invalid/v1', 'model': 'mock', 'apiKey': 'test-only'}
        with patch.object(suggestions.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(response).encode())) as model:
            result = suggestions.suggest(papers, config)
            prompt = json.loads(model.call_args.args[0].data)['messages'][1]['content']
            self.assertIn('BIO1', prompt); self.assertIn('BIO2', prompt)
            self.assertNotIn('do not send', prompt)
            self.assertEqual(result['goal'], draft['goal'])
            self.assertFalse(result['saved'])
        self.assertFalse(rp.PROFILE_PATH.exists())
        for keys in ([], ['A'] * 2, ['A'] * 6, ['../data'], [True], 'A'):
            with self.assertRaises(ValueError): suggestions.selected_papers(store, {'keys': keys})
        store.item.return_value = None; store.item.side_effect = None
        with self.assertRaises(FileNotFoundError): suggestions.selected_papers(store, {'keys': ['MISSING']})

    def test_invalid_or_truncated_answer_never_changes_saved_goal(self):
        old = rp.save_profile({'goal': 'Preserve my topic'})
        config = {'configured': True, 'baseUrl': 'https://example.invalid', 'model': 'mock', 'apiKey': ''}
        for content, finish in [('{}', 'stop'), ('{"goal":"unfinished', 'length'), (None, 'stop')]:
            payload = {'choices': [{'message': {'content': content}, 'finish_reason': finish}]}
            with patch.object(suggestions.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(payload).encode())) as model:
                with self.assertRaisesRegex(RuntimeError, '未修改研究方向'):
                    suggestions.suggest([], config)
                self.assertEqual(model.call_count, 1)
                self.assertEqual(rp.profile(), old)
        with patch.object(suggestions, 'request_jobs') as jobs:
            jobs.urlopen.side_effect = request_jobs.Cancelled('cancelled')
            jobs.Cancelled = request_jobs.Cancelled
            with self.assertRaises(request_jobs.Cancelled): suggestions.suggest([], config)

    def test_http_empty_goal_blocks_paid_assessment_and_suggestion_is_preview_only(self):
        store = Mock(); store.demo = False
        store.item.return_value = {'key': 'TEST', 'title': 'Genomics', 'abstract': ''}
        httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        worker = threading.Thread(target=httpd.serve_forever, daemon=True); worker.start()
        def post(path, body):
            request = urllib.request.Request(f'http://127.0.0.1:{httpd.server_port}' + path,
                data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request) as response: return json.load(response)
        try:
            with patch.object(server, 'STORE', store), patch.object(server, 'load_analysis', return_value={}), patch.object(server, 'generate_priority') as generate:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    post('/api/items/TEST/priority', {'action': 'evaluate', 'profileVersion': rp.profile()['version']})
                self.assertEqual(error.exception.code, 400); generate.assert_not_called()
                result = post('/api/items/TEST/priority', {'action': 'manual', 'tier': '夯', 'profileVersion': rp.profile()['version']})
                self.assertEqual(result['tier'], '夯')
                with patch.object(suggestions, 'suggest', return_value={'goal': 'Draft', 'saved': False}) as suggest:
                    self.assertFalse(post('/api/research/suggest', {'keys': ['TEST']})['saved'])
                    self.assertEqual(suggest.call_args.args[0][0]['key'], 'TEST')
                self.assertFalse(rp.PROFILE_PATH.exists())
        finally:
            httpd.shutdown(); httpd.server_close(); worker.join(timeout=2)


if __name__ == '__main__': unittest.main()
