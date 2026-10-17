"""Verify region images and cache reuse without calling a model provider."""
import base64
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
        self.assertEqual(result["figure"]["region"], [500, 0, 500, 1000])

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
