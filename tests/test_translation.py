"""Professional terminology, contextual caching and API; model calls mocked."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('reviewer_translation', Path(__file__).resolve().parents[1] / 'scripts/server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
translation = server.translation


class TranslationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        for attribute, value in [('GLOSSARY_PATH', directory / 'glossary.json'), ('CACHE_DIR', directory / 'cache')]:
            patcher = patch.object(translation, attribute, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.item = {'key': 'TEST', 'title': 'Coronagraph design', 'abstract': 'Starlight suppression.'}
        self.config = {'configured': True, 'model': 'deepseek-flash', 'baseUrl': 'https://api.deepseek.com', 'apiKey': 'fake-test-only'}

    def response(self, text='日冕仪抑制恒星光。'):
        result = {'translation': text, 'explanation': '在高对比度成像中的光学装置。', 'uncertainty': ''}
        return io.BytesIO(json.dumps({'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(result)}}]}).encode())

    def test_exact_terminology_and_plural_do_not_call_model(self):
        with patch.object(translation.urllib.request, 'urlopen') as call:
            for word in ('coronagraph', 'Coronagraph', 'coronagraphs'):
                result = translation.translate(self.item, {'text': word}, {'configured': False})
                self.assertEqual(result['translation'], '日冕仪')
                self.assertEqual(result['method'], 'glossary')
            call.assert_not_called()
        self.assertEqual(translation.matched('coronagraphic measurements'), [])

    def test_personal_correction_persists_and_enters_deep_reading_prompt(self):
        before = translation.glossary()['version']
        translation.save_term({'term': 'adaptive optics', 'translation': '自适应光学', 'note': '天文光学'})
        self.assertNotEqual(before, translation.glossary()['version'])
        text = server.deep_reading.prompt(self.item, 'overview', [], {})
        self.assertIn('自适应光学', text)
        self.assertIn('日冕仪', text)
        translation.save_term({'term': 'coronagraph', 'translation': '日冕仪', 'note': '个人领域说明'})
        self.assertEqual(translation.translate(self.item, {'text': 'coronagraphs'}, {})['explanation'], '个人领域说明')

    def test_contextual_translation_is_cached_and_glossary_change_invalidates(self):
        payload = {'text': 'The coronagraph suppresses starlight.', 'context': 'Exoplanet imaging.'}
        with patch.object(translation.urllib.request, 'urlopen', side_effect=lambda *a, **k:self.response()) as call:
            result = translation.translate(self.item, payload, self.config)
            self.assertFalse(result['cached'])
            request = json.loads(call.call_args.args[0].data)
            self.assertIn('Exoplanet imaging.', request['messages'][-1]['content'])
            self.assertIn('日冕仪', request['messages'][-1]['content'])
            self.assertEqual(request['thinking'], {'type': 'disabled'})
            self.assertTrue(translation.translate(self.item, payload, self.config)['cached'])
            self.assertEqual(call.call_count, 1)
            translation.save_term({'term': 'starlight', 'translation': '恒星光'})
            translation.translate(self.item, payload, self.config)
            self.assertEqual(call.call_count, 2)
            translation.translate(self.item, {**payload, 'context': 'Different context'}, self.config)
            self.assertEqual(call.call_count, 3)

    def test_failed_explicit_retry_keeps_successful_cache(self):
        payload = {'text': 'A coronagraph suppresses starlight.'}
        with patch.object(translation.urllib.request, 'urlopen', side_effect=lambda *a, **k:self.response()) as call:
            translation.translate(self.item, payload, self.config)
            call.side_effect = lambda *a, **k:io.BytesIO(b'{"choices":[]}')
            with self.assertRaises(RuntimeError):
                translation.translate(self.item, {**payload, 'force': True}, self.config)
            self.assertTrue(translation.translate(self.item, payload, self.config)['cached'])
            self.assertEqual(call.call_count, 2)

    def test_invalid_selections_and_uncertain_terms_are_explicit(self):
        for invalid in ({'text': ''}, {'text': 'x' * 2001}, {'text': []}, {'text': 'x', 'context': 'y' * 6001}):
            with self.assertRaises(ValueError):
                translation.validate(invalid)
        with patch.object(translation.urllib.request, 'urlopen', side_effect=lambda *a, **k:self.response('装置抑制星光。')):
            result = translation.translate(self.item, {'text': 'The coronagraph suppresses starlight.'}, self.config)
            self.assertIn('日冕仪', result['notices'][0])

    def test_http_pdf_context_and_attachment_ownership(self):
        store = Mock()
        store.item.return_value = {**self.item, 'attachments': [{'key': 'PDF'}]}
        store.pdf_page.return_value = {'text': 'Original PDF page context', 'page': 2}
        http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        self.addCleanup(http.server_close)
        self.addCleanup(http.shutdown)
        url = f'http://127.0.0.1:{http.server_port}/api/items/TEST/translate'
        def post(payload):
            request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
            return json.loads(urllib.request.urlopen(request).read())
        with patch.object(server, 'STORE', store), patch.object(server, 'model_config', return_value={'configured': False}):
            self.assertEqual(post({'text': 'coronagraph', 'attachmentKey': 'PDF', 'page': 2})['translation'], '日冕仪')
            with self.assertRaises(urllib.error.HTTPError) as error:
                post({'text': 'coronagraph', 'attachmentKey': 'OTHER', 'page': 2})
            self.assertEqual(error.exception.code, 400)
            with patch.object(translation, 'translate', return_value={'translation': 'fixture'}) as translate:
                post({'text': 'some phrase', 'attachmentKey': 'PDF', 'page': 2, 'context': 'untrusted browser context'})
                self.assertEqual(translate.call_args.args[1]['context'], 'Original PDF page context')


if __name__ == '__main__':
    unittest.main()
