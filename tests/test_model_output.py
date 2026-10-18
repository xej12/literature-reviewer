"""Repair real-world formatting without completing or rewriting paper claims."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("reviewer_output", Path(__file__).resolve().parents[1] / "scripts/server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
output = server.model_output
deep = server.deep_reading


class OutputTests(unittest.TestCase):
    def chapter(self, body="Explanation"):
        return {"intro": "Read", "blocks": [{"title": "Mechanism", "body": body, "basis": "paper", "sourceIds": ["P0001C001"]}]}

    def test_fences_prose_multiblock_and_reasoning_wrapper(self):
        value = self.chapter()
        text = '<think>not an answer {ignore}</think>\nHere is the result:\n```json\n' + json.dumps(value) + '\n```\nDone.'
        self.assertEqual(output.parse_chapter(text)[0], value)
        self.assertEqual(output.parse_chapter([{"type": "text", "text": json.dumps(value)}])[0], value)
        self.assertEqual(output.visible_text('<think>incomplete reasoning'), '')

    def test_valid_escaped_formula_and_prose_are_unchanged(self):
        for body in [r'$\frac{a}{b}+\beta+\theta+\nu+\rho$', '$λ + β$', '$x\n y$', 'First line\nnext line\tTabbed\n"quoted"', r'\[\mathbf{E}=\begin{bmatrix}x\end{bmatrix}\]']:
            value = self.chapter(body)
            parsed, notes = output.parse_chapter(json.dumps(value, ensure_ascii=False))
            self.assertEqual(parsed, value)
            self.assertEqual(notes, [])

    def test_invalid_math_escapes_do_not_silently_corrupt_valid_json(self):
        text = r'{"intro":"Read","blocks":[{"title":"Math","body":"$\frac{a}{b}+\beta+\theta+\nu+\rho+\alpha$","basis":"paper","sourceIds":["P0001C001"]}]}'
        parsed, notes = output.parse_chapter(text)
        self.assertEqual(parsed['blocks'][0]['body'], r'$\frac{a}{b}+\beta+\theta+\nu+\rho+\alpha$')
        self.assertTrue(notes)
        self.assertNotIn('\x08', parsed['blocks'][0]['body'])
        self.assertNotIn('\x0c', parsed['blocks'][0]['body'])

    def test_raw_newlines_and_trailing_commas_preserve_values(self):
        text = '{"intro":"Read", "blocks":[{"title":"Math", "body":"line one\nline two, } stays literal", "basis":"paper", "sourceIds":["P0001C001",],},],}'
        parsed, notes = output.parse_chapter(text)
        self.assertEqual(parsed['blocks'][0]['body'], 'line one\nline two, } stays literal')
        self.assertEqual(parsed['blocks'][0]['sourceIds'], ['P0001C001'])
        self.assertGreaterEqual(len(notes), 2)

    def test_truncation_and_unquoted_claims_are_not_invented(self):
        for text, reason in [(json.dumps(self.chapter())[:-7], None), (json.dumps(self.chapter()), 'length'), ('A plain text answer.', None), ('{"intro": "He said "no"."}', None)]:
            with self.assertRaises(ValueError):
                output.parse_chapter(text, reason)

    def test_draft_saved_recovered_locally_and_never_calls_model_twice(self):
        item = {"key": "TEST", "title": "Paper"}
        corpus = deep.build_corpus(item, "PDF", ["Paper method and results. " * 35])
        store = Mock()
        store.deep_corpus.return_value = item, corpus
        config = {"configured": True, "model": "mock", "baseUrl": "https://example.invalid/v1", "apiKey": "mock-key"}
        raw = '{"intro":"unfinished"'
        response = {"choices": [{"finish_reason": "length", "message": {"content": raw}}]}
        with tempfile.TemporaryDirectory() as directory, patch.object(server, "STORE", store), patch.object(server, "DEEP_READING_DIR", Path(directory)), patch.object(server, "model_config", return_value=config) as get_config, patch.object(server.urllib.request, "urlopen", side_effect=lambda *a, **k: io.BytesIO(json.dumps(response).encode())) as model:
            result = server.generate_deep_chapter("TEST", "methods")
            self.assertTrue(result['pending'])
            draft = result['reading']['drafts']['methods']
            self.assertEqual(draft['content'], raw)
            self.assertIn('长度限制', draft['formatError'])
            again = server.generate_deep_chapter("TEST", "methods")
            self.assertTrue(again['pending'])
            self.assertEqual(model.call_count, 1)
            self.assertEqual(get_config.call_count, 1)
            self.assertEqual(deep.load(Path(directory), "TEST")['versions'][0]['sections'], {})
            self.assertTrue(server.generate_deep_chapter("TEST", "overview", repair_only=True)['noDraft'])
            self.assertEqual(model.call_count, 1)
            # Simulate a cached answer that a newer parser can recover for free.
            draft.update(content='Here is the JSON:\n```json\n' + json.dumps(self.chapter()) + '\n```', finishReason='stop')
            deep.save_section(Path(directory), "TEST", corpus, "methods", draft, draft=True)
            repaired = server.generate_deep_chapter("TEST", "methods", repair_only=True)
            self.assertFalse(repaired['pending'])
            self.assertTrue(repaired['cached'])
            self.assertEqual(repaired['reading']['sections']['methods']['blocks'][0]['sources'][0]['page'], 1)
            self.assertNotIn('methods', repaired['reading']['drafts'])
            self.assertEqual(model.call_count, 1)


if __name__ == '__main__':
    unittest.main()
