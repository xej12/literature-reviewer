"""Output budgeting and provider reasoning options; all model calls mocked."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("reviewer_generation", Path(__file__).resolve().parents[1] / "scripts/server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
generation = server.generation


class GenerationTests(unittest.TestCase):
    def config(self, **overrides):
        return {"configured": True, "baseUrl": "https://api.deepseek.com", "model": "deepseek-flash", "apiKey": "test-not-a-key", **overrides}

    def test_default_deepseek_preserves_service_thinking_budget(self):
        config = self.config()
        options = generation.request_options(config)
        self.assertNotIn('max_tokens', options)
        self.assertNotIn('reasoning_effort', options)
        self.assertNotIn('thinking', options)
        self.assertNotIn('temperature', options)
        self.assertEqual(options['response_format'], {'type': 'json_object'})
        self.assertIn('64K', generation.profile(config)['budgetLabel'])
        self.assertIn('128K', generation.profile(self.config(thinkingMode='max'))['budgetLabel'])

    def test_explicit_budget_and_thinking_modes_do_not_leak_to_other_providers(self):
        options = generation.request_options(self.config(maxOutputTokens=131072, thinkingMode='max'))
        self.assertEqual(options['max_tokens'], 131072)
        self.assertEqual(options['thinking'], {'type': 'enabled'})
        self.assertEqual(options['reasoning_effort'], 'max')
        self.assertEqual(generation.request_options(self.config(thinkingMode='off'))['thinking'], {'type': 'disabled'})
        for url in ('https://example.invalid/v1', 'https://api.deepseek.com.example.invalid'):
            generic = generation.request_options(self.config(baseUrl=url))
            self.assertEqual(generic, {'temperature': 0.2})
        for invalid in (True, 800, 400000, 1.2, 'twelve', [], {}):
            with self.assertRaises(ValueError):
                generation.settings({'maxOutputTokens': invalid})
        with self.assertRaises(ValueError):
            generation.settings({'thinkingMode': {}})

    def test_save_settings_preserves_key_and_omitted_existing_options(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(server, 'SETTINGS_PATH', Path(directory) / 'settings.json'), patch.dict(server.os.environ, {}, clear=True):
            stored = server.save_model_config({**self.config(), 'maxOutputTokens': 65536, 'thinkingMode': 'high'})
            self.assertNotIn('apiKey', stored)
            self.assertNotIn('test-not-a-key', json.dumps(stored))
            raw_settings = (Path(directory) / 'settings.json').read_text(encoding='utf-8')
            self.assertNotIn('test-not-a-key', raw_settings)
            self.assertTrue((Path(directory) / 'model-key.bin').is_file())
            self.assertEqual(stored['generation']['maxOutputTokens'], 65536)
            server.save_model_config({'baseUrl': 'https://api.deepseek.com/v1', 'model': 'deepseek-flash', 'apiKey': ''})
            saved = server.saved_model_config()
            self.assertEqual(saved['apiKey'], 'test-not-a-key')
            self.assertEqual(saved['maxOutputTokens'], 65536)
            self.assertEqual(saved['thinkingMode'], 'high')
            server.save_model_config({'baseUrl': 'https://api.deepseek.com', 'model': 'deepseek-flash', 'apiKey': '', 'maxOutputTokens': None, 'thinkingMode': 'auto'})
            self.assertIsNone(server.model_config()['maxOutputTokens'])
            self.assertTrue(server.public_model_config(server.model_config())['generation']['thinkingSupported'])

    def test_model_probe_uses_models_endpoint_without_prompt(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"data":[{"id":"deepseek-chat"}]}'
        with patch.object(server.urllib.request, 'urlopen', return_value=response) as request:
            result = server.test_model_connection({'baseUrl': 'https://api.deepseek.com/v1', 'model': 'deepseek-chat', 'apiKey': 'probe-key'})
        self.assertTrue(result['ok']); self.assertFalse(result['billable'])
        sent = request.call_args.args[0]
        self.assertTrue(sent.full_url.endswith('/models'))
        self.assertEqual(sent.get_header('Authorization'), 'Bearer probe-key')

    def test_real_request_has_no_8000_cap_and_saves_usage_without_reasoning(self):
        item = {'key': 'TEST', 'title': 'Paper'}
        corpus = server.deep_reading.build_corpus(item, 'PDF', ['Methods and experimental evidence. ' * 50])
        store = Mock()
        store.deep_corpus.return_value = item, corpus
        answer = {'intro': 'Read deeply', 'blocks': [{'title': 'Method', 'body': 'Inputs, operations and outputs explained.', 'basis': 'paper', 'sourceIds': ['P0001C001']}]}
        responses = [
            {'choices': [{'finish_reason': 'length', 'message': {'content': '', 'reasoning_content': 'PRIVATE REASONING'}}],
             'usage': {'completion_tokens': 8000, 'completion_tokens_details': {'reasoning_tokens': 8000}}},
            {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(answer), 'reasoning_content': 'PRIVATE REASONING'}}],
             'usage': {'prompt_tokens': 100, 'completion_tokens': 11000, 'completion_tokens_details': {'reasoning_tokens': 9500}}},
        ]
        def response(*args, **kwargs):
            return io.BytesIO(json.dumps(responses.pop(0)).encode())
        with tempfile.TemporaryDirectory() as directory, patch.object(server, 'STORE', store), patch.object(server, 'DEEP_READING_DIR', Path(directory)), patch.object(server, 'model_config', return_value=self.config()), patch.object(server.urllib.request, 'urlopen', side_effect=response) as model:
            first = server.generate_deep_chapter('TEST', 'methods')
            self.assertTrue(first['pending'])
            draft = first['reading']['drafts']['methods']
            self.assertIn('正文前', draft['formatError'])
            self.assertEqual(draft['usage']['reasoningTokens'], 8000)
            self.assertNotIn('PRIVATE REASONING', json.dumps(first))
            repaired = server.generate_deep_chapter('TEST', 'methods', force=True)
            self.assertFalse(repaired['pending'])
            chapter = repaired['reading']['sections']['methods']
            self.assertEqual(chapter['usage']['completionTokens'], 11000)
            self.assertNotIn('PRIVATE REASONING', json.dumps(repaired))
            for call in model.call_args_list:
                body = json.loads(call.args[0].data)
                self.assertNotIn('max_tokens', body)
                self.assertEqual(body['response_format']['type'], 'json_object')
                self.assertEqual(call.kwargs['timeout'], 600)
            self.assertTrue(server.generate_deep_chapter('TEST', 'methods')['cached'])
            self.assertEqual(model.call_count, 2)


if __name__ == '__main__':
    unittest.main()
