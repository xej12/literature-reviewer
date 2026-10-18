"""Verify region images and cache reuse without calling a model provider."""
import base64
import copy
from concurrent.futures import ThreadPoolExecutor
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

from PIL import Image

spec = importlib.util.spec_from_file_location("reviewer", Path(__file__).resolve().parents[1] / "scripts/server.py")
reviewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reviewer)


class FigureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.store = Mock()
        self.store.pdf_page.return_value = {'page':2, 'pageCount':4}
        self.value = {'intro':'Understand this plot', 'blocks':[
            {'title':'Read the axes', 'body':'Visible axis and units. $I=|E|^2$', 'basis':'image', 'anchor':'Left panel, vertical axis'},
            {'title':'Teaching example', 'body':'These numbers are illustrative.', 'basis':'background', 'anchor':''}]}
        self.draft = {'title':'Paper', 'attachmentKey':'PDF', 'page':2, 'pageCount':4, 'region':None,
                      'content':json.dumps(self.value), 'finishReason':'stop', 'attemptId':'fixture', 'model':'mock-only'}

    def test_model_receives_selected_pixels_only(self):
        source = Image.new("RGB", (200, 100), "red")
        source.paste("blue", (100, 0, 200, 100))
        stream = io.BytesIO()
        source.save(stream, format="PNG")
        store = Mock()
        store.item.return_value = {"key": "TEST", "title": "Paper"}
        store.pdf_page.return_value = {"page": 1, "pageCount": 3}
        store.pdf_page_image.return_value = stream.getvalue()
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({"choices": [{"message": {"content": '{"description":"test"}'}}]}).encode()
        with patch.object(reviewer, "STORE", store), patch.object(reviewer, "model_config", return_value={"configured": True, "baseUrl": "http://example.invalid", "model": "test", "apiKey": "test"}), patch.object(reviewer.urllib.request, "urlopen", return_value=response) as send:
            result = reviewer.generate_figure("TEST", "PDF", 1, [500, 0, 500, 1000])
        body = json.loads(send.call_args.args[0].data)
        image_url = body["messages"][1]["content"][1]["image_url"]["url"]
        with Image.open(io.BytesIO(base64.b64decode(image_url.split(",", 1)[1]))) as cropped:
            self.assertEqual(cropped.size, (100, 100))
            self.assertEqual(cropped.getpixel((0, 0)), (0, 0, 255))
        self.assertEqual(result["figureDraft"]["region"], [500, 0, 500, 1000])
        instruction = body['messages'][1]['content'][0]['text']
        for requirement in ('只', '对数刻度', '误差棒', '流程/光路图', 'inference', '自检问题', '图中无法确认'):
            self.assertIn(requirement, instruction)

    def test_paid_text_saved_before_parse_and_reopen_is_free(self):
        def normalize(value):
            stored = reviewer.load_analysis('TEST')['figureDrafts']['PDF:2']
            self.assertEqual(stored['content'], self.draft['content'])
            return original_normalize(value)
        original_normalize = reviewer.figure_reading.normalize
        with patch.object(reviewer,'STORE',self.store), patch.object(reviewer,'ANALYSIS_DIR',self.directory), \
             patch.object(reviewer,'generate_figure',return_value={'figureDraft':self.draft}) as model, \
             patch.object(reviewer.figure_reading,'normalize',side_effect=normalize):
            result = reviewer.figure_lesson('TEST','PDF',2,None)
            self.assertFalse(result['cached'])
            self.assertEqual(result['figure']['blocks'][0]['basis'],'image')
            self.assertFalse(result['figureDrafts'])
            self.assertTrue(reviewer.figure_lesson('TEST','PDF',2,None)['cached'])
            self.assertEqual(model.call_count,1)
            self.assertEqual(len(result['figureAttempts']['PDF:2']),1)

    def test_failed_regeneration_keeps_history_and_local_repair_costs_nothing(self):
        legacy = {'description':'Original saved interpretation','attachmentKey':'PDF','page':2}
        broken = {**self.draft, 'content':'{"blocks": ['}
        with patch.object(reviewer,'STORE',self.store), patch.object(reviewer,'ANALYSIS_DIR',self.directory), \
             patch.object(reviewer,'generate_figure',return_value={'figureDraft':broken}) as model:
            reviewer.save_figure('TEST','PDF:2',{'figure':legacy})
            failed = reviewer.figure_lesson('TEST','PDF',2,None,force=True)
            self.assertTrue(failed['figurePending'])
            self.assertEqual(failed['figures']['PDF:2'],legacy)
            self.assertIn('PDF:2',failed['figureDrafts'])
            self.assertTrue(reviewer.figure_lesson('TEST','PDF',2,None,repair_only=True)['figurePending'])
            self.assertEqual(model.call_count,1)
            # Simulate parser repairability without another model request.
            repaired = {**broken, 'content':json.dumps(self.value) + ','}
            reviewer.save_figure_draft('TEST','PDF:2',repaired)
            success = reviewer.figure_lesson('TEST','PDF',2,None,repair_only=True)
            self.assertFalse(success['figurePending'])
            self.assertEqual(success['figureHistory']['PDF:2'],[legacy])
            self.assertEqual(model.call_count,1)
            self.assertTrue(reviewer.figure_lesson('TEST','PDF',2,None,force=True,repair_only=True)['noDraft'])
            self.assertEqual(model.call_count,1)

    def test_truncation_never_overwrites_success_and_double_requests_bill_once(self):
        with patch.object(reviewer,'STORE',self.store), patch.object(reviewer,'ANALYSIS_DIR',self.directory), \
             patch.object(reviewer,'generate_figure',return_value={'figureDraft':self.draft}) as model:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _:reviewer.figure_lesson('TEST','PDF',2,None),range(2)))
            self.assertEqual(model.call_count,1)
            self.assertEqual(sorted(r['cached'] for r in results),[False,True])
            before = copy.deepcopy(results[0]['figures'])
            model.return_value = {'figureDraft':{**self.draft,'finishReason':'length','attemptId':'truncated'}}
            failed = reviewer.figure_lesson('TEST','PDF',2,None,force=True)
            self.assertTrue(failed['figurePending'])
            self.assertEqual(failed['figures'],before)
            self.assertIn('长度限制',failed['figureDrafts']['PDF:2']['formatError'])

    def test_empty_or_mixed_basis_results_are_not_adopted(self):
        for value in ({}, {'blocks':[]}, {'blocks':[{'title':'x','body':'y','basis':'verified'}]}):
            with self.assertRaises(ValueError):
                reviewer.figure_reading.normalize(value)
        legacy = {key:'Saved short field' for key in ('description','trends','takeaway','caveats')}
        self.assertIn('notices',reviewer.figure_reading.normalize(legacy))

    def test_repair_without_draft_and_malformed_upstream_never_trigger_retry(self):
        source = Image.new('RGB',(20,20),'white')
        stream = io.BytesIO(); source.save(stream,format='PNG')
        self.store.item.return_value = {'key':'TEST','title':'Paper'}
        self.store.pdf_page_image.return_value = stream.getvalue()
        config = {'configured':True,'baseUrl':'http://model.invalid','model':'mock-only','apiKey':'fake-test-key','maxOutputTokens':16384}
        with patch.object(reviewer,'STORE',self.store), patch.object(reviewer,'ANALYSIS_DIR',self.directory), \
             patch.object(reviewer,'model_config',return_value=config), \
             patch.object(reviewer.urllib.request,'urlopen',return_value=io.BytesIO(b'<html>Upstream format error</html>')) as model:
            self.assertTrue(reviewer.figure_lesson('TEST','PDF',2,None,repair_only=True)['noDraft'])
            model.assert_not_called()
            result = reviewer.figure_lesson('TEST','PDF',2,None)
            self.assertTrue(result['figurePending'])
            self.assertEqual(result['figureDrafts']['PDF:2']['content'],'<html>Upstream format error</html>')
            self.assertEqual(model.call_count,1)
            self.assertEqual(json.loads(model.call_args.args[0].data)['max_tokens'],16384)
            self.assertTrue(reviewer.figure_lesson('TEST','PDF',2,None)['figurePending'])
            self.assertEqual(model.call_count,1)

    def test_cached_region_never_calls_model_and_keeps_other_results(self):
        region = [100, 200, 300, 400]
        key = reviewer.figure_cache_key("PDF", 2, region)
        figure = {"attachmentKey": "PDF", "page": 2, "region": region, "description": "Saved"}
        store = Mock()
        store.item.return_value = {"attachments": [{"key": "PDF"}]}
        store.pdf_page.return_value = {"page": 2}
        with tempfile.TemporaryDirectory() as directory, patch.object(reviewer, "ANALYSIS_DIR", Path(directory)), patch.object(reviewer, "STORE", store), patch.object(reviewer, "generate_figure", side_effect=AssertionError("Model must not be called")):
            reviewer.save_analysis("TEST", "summary", {"summary": {"findings": "Keep"}})
            reviewer.save_figure("TEST", "PDF:2", {"figure": {"description": "Whole page"}})
            reviewer.save_figure("TEST", key, {"figure": figure})
            server = reviewer.ThreadingHTTPServer(("127.0.0.1", 0), reviewer.Handler)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/api/items/TEST/figure"
                payload = {"attachmentKey": "PDF", "page": 2, "region": region}
                request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request) as response:
                    saved = json.load(response)
                self.assertTrue(saved["cached"])
                self.assertEqual(saved["figure"], figure)
                self.assertEqual(saved["summary"]["findings"], "Keep")
                self.assertEqual(len(saved["figures"]), 2)
                payload["region"] = [900, 0, 200, 100]
                request = urllib.request.Request(url, data=json.dumps(payload).encode())
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request)
                self.assertEqual(error.exception.code, 400)
            finally:
                server.shutdown()
                server.server_close()
                worker.join()


if __name__ == "__main__":
    unittest.main()
