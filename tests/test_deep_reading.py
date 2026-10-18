"""Deep reading source coverage, caching and API contract; never paid calls."""
import copy
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("reviewer_deep", Path(__file__).resolve().parents[1] / "scripts/server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
deep = server.deep_reading


class DeepReadingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.item = {"key": "TEST", "title": "Wavefront control methods", "doi": "10.1234/test"}
        self.pages = [f"Page {p}. The optical method measures the field and controls the residual. " * 8 for p in range(1, 19)]
        self.corpus = deep.build_corpus(self.item, "PDF", self.pages)
        self.store = Mock()
        self.store.deep_corpus.return_value = (self.item, self.corpus)
        self.config = {"configured": True, "model": "test-model", "baseUrl": "https://model.invalid/v1", "apiKey": "fake-for-tests"}

    def output(self, source_id="P0018C001"):
        return {"intro": "Understand the measurement and control loop.", "blocks": [
            {"title": "Measurement", "body": "An explanation of input, operation and output. $I=|E|^2$", "basis": "paper", "sourceIds": [source_id]},
            {"title": "Teaching example", "body": "These illustrative values are not paper measurements.", "basis": "background", "sourceIds": []},
        ]}

    def response(self, value):
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": json.dumps(value)}}]}).encode())

    def test_full_pdf_and_long_pdf_report_actual_coverage(self):
        chunks, coverage = deep.select_context(self.corpus, "methods")
        self.assertEqual(coverage["includedPages"], list(range(1, 19)))
        self.assertFalse(coverage["partial"])
        self.assertIn("P0018C001", [c["id"] for c in chunks])
        selected, limited = deep.select_context(self.corpus, "methods", max_chars=3500)
        self.assertTrue(limited["partial"])
        self.assertIn(18, limited["includedPages"])
        self.assertEqual(limited["includedPages"], sorted({c["page"] for c in selected}))
        self.assertLessEqual(sum(len(c["text"]) + len(c["id"]) + 30 for c in selected), 3500)
        self.assertLess(limited["includedChunks"], limited["totalChunks"])

    def test_missing_text_is_explicit_and_scans_cannot_trigger_generation(self):
        mixed = deep.build_corpus(self.item, "PDF", [self.pages[0], "", self.pages[-1]])
        _, coverage = deep.select_context(mixed, "overview")
        self.assertEqual(coverage["emptyPages"], [2])
        self.assertEqual(coverage["readablePages"], [1, 3])
        with self.assertRaisesRegex(ValueError, "正文不足"):
            deep.build_corpus(self.item, "PDF", ["", "scanned"])
        with self.assertRaisesRegex(ValueError, "正文不足"):
            deep.build_corpus(self.item, "PDF", ["Journal header and page number"] * 50)

    def test_zotero_attachment_extraction_uses_all_pages(self):
        store = server.ZoteroStore.__new__(server.ZoteroStore)
        store.item = Mock(return_value={**self.item, "attachments": [{"key": "PDF", "exists": True, "contentType": "application/pdf"}]})
        store.pdf_page = Mock(return_value={"page": 1})
        store._pdf_cache = {"PDF": {"pages": self.pages}}
        _, corpus = store.deep_corpus("TEST")
        self.assertEqual(corpus["pageCount"], 18)
        self.assertEqual(corpus["chunks"][-1]["page"], 18)
        store.item.return_value["attachments"] = []
        with self.assertRaisesRegex(ValueError, "本地 PDF"):
            store.deep_corpus("TEST")

    def test_citations_use_only_sent_chunks_and_keep_unverified_output(self):
        selected = self.corpus["chunks"][:1]
        output = self.output()
        result = deep.normalize_result(output, "methods", selected)
        self.assertTrue(result["blocks"][0]["unverified"])
        self.assertFalse(result["blocks"][0]["sources"])
        self.assertTrue(result["notices"])
        self.assertFalse(result["blocks"][1]["unverified"])
        output["blocks"][0]["sourceIds"] = ["P0001C001", "P0001C001"]
        verified = deep.normalize_result(output, "methods", selected)
        self.assertEqual(verified["blocks"][0]["sources"], selected)
        self.assertFalse(verified["notices"])
        for invalid in ([], "wrong", {"blocks": []}, {"blocks": [{"title": "bad", "body": "text", "basis": "fact"}]}):
            with self.assertRaises(ValueError):
                deep.normalize_result(invalid, "methods", selected)

    def test_formula_teaching_requires_original_notation_and_separate_examples(self):
        chunks, coverage = deep.select_context(self.corpus, "formulas")
        instruction = deep.prompt(self.item, "formulas", chunks, coverage)
        for requirement in ("原文式（实际编号）", "上下标", "控制字符", "每个符号", "补充教学公式", "双重转义"):
            self.assertIn(requirement, instruction)

    def test_generation_cache_history_and_invalid_regeneration_keep_legacy(self):
        legacy_dir = self.directory / "legacy"
        with patch.object(server, "STORE", self.store), patch.object(server, "DEEP_READING_DIR", self.directory / "deep"), patch.object(server, "ANALYSIS_DIR", legacy_dir), patch.object(server, "model_config", return_value=self.config), patch.object(server.urllib.request, "urlopen", side_effect=lambda *a, **k: self.response(self.output())) as model:
            server.save_analysis("TEST", "summary", {"summary": {"methods": "Original saved summary"}})
            initial = server.generate_deep_chapter("TEST", "methods")
            self.assertFalse(initial["cached"])
            self.assertEqual(initial["reading"]["sections"]["methods"]["blocks"][0]["sources"][0]["page"], 18)
            request = json.loads(model.call_args.args[0].data)
            self.assertIn("[P0018C001]", request["messages"][-1]["content"])
            self.assertIn("输入", request["messages"][-1]["content"])
            self.assertEqual(initial["reading"]["sections"]["methods"]["model"], "test-model")
            self.assertTrue(server.generate_deep_chapter("TEST", "methods")["cached"])
            self.assertEqual(model.call_count, 1)
            server.generate_deep_chapter("TEST", "overview")
            regenerated = server.generate_deep_chapter("TEST", "methods", True)
            self.assertEqual(len(regenerated["reading"]["history"]["methods"]), 1)
            self.assertIn("overview", regenerated["reading"]["sections"])
            before = copy.deepcopy(regenerated["reading"])
            model.side_effect = lambda *a, **k: self.response({"blocks": []})
            pending = server.generate_deep_chapter("TEST", "methods", True)
            self.assertTrue(pending["pending"])
            stored = deep.current_reading(server.DEEP_READING_DIR, "TEST", self.corpus)
            self.assertEqual(stored["sections"], before["sections"])
            self.assertEqual(stored["history"], before["history"])
            self.assertIn('"blocks": []', stored["drafts"]["methods"]["content"])
            self.assertEqual(server.load_analysis("TEST")["summary"]["methods"], "Original saved summary")

    def test_double_requests_only_call_model_once(self):
        with patch.object(server, "STORE", self.store), patch.object(server, "DEEP_READING_DIR", self.directory), patch.object(server, "model_config", return_value=self.config), patch.object(server.urllib.request, "urlopen", side_effect=lambda *a, **k: self.response(self.output())) as model:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: server.generate_deep_chapter("TEST", "methods"), range(2)))
            self.assertEqual(model.call_count, 1)
            self.assertEqual(sorted(r["cached"] for r in results), [False, True])

    def test_changed_pdf_creates_new_version_and_keeps_prior_results(self):
        value = {"blocks": [], "generatedAt": "test"}
        deep.save_section(self.directory, "TEST", self.corpus, "methods", value)
        changed = deep.build_corpus(self.item, "PDF", self.pages + ["Appendix results. " * 70])
        self.assertEqual(deep.current_reading(self.directory, "TEST", changed)["sections"], {})
        deep.save_section(self.directory, "TEST", changed, "overview", value)
        self.assertEqual(len(deep.load(self.directory, "TEST")["versions"]), 2)
        self.assertEqual(deep.current_reading(self.directory, "TEST", self.corpus)["sections"]["methods"], value)
        # A changed diagram/formula image can change PDF bytes while leaving
        # extracted text identical; that must invalidate the reading too.
        image_changed = deep.build_corpus(self.item, "PDF", self.pages, "different-pdf-bytes")
        self.assertNotEqual(image_changed["fingerprint"], self.corpus["fingerprint"])

    def test_api_get_cached_post_and_progress_never_call_model(self):
        with patch.object(server, "STORE", self.store), patch.object(server, "DEEP_READING_DIR", self.directory), patch.object(server, "ANALYSIS_DIR", self.directory / "legacy"), patch.object(server, "model_config", side_effect=AssertionError("No model configuration needed to view cache")):
            deep.save_section(self.directory, "TEST", self.corpus, "methods", {"title": "Saved", "blocks": []})
            http = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            worker = threading.Thread(target=http.serve_forever, daemon=True)
            worker.start()
            try:
                url = f"http://127.0.0.1:{http.server_port}/api/items/TEST/deep-reading"
                with urllib.request.urlopen(url) as response:
                    data = json.load(response)
                self.assertEqual(len(data["chapters"]), 5)
                self.assertEqual(data["source"]["pageCount"], 18)
                request = urllib.request.Request(url, data=json.dumps({"section": "methods"}).encode(), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request) as response:
                    self.assertTrue(json.load(response)["cached"])
                self.assertTrue(server.analysis_status("TEST")["summary"])
                self.store.deep_corpus.side_effect = ValueError("PDF no longer available")
                with urllib.request.urlopen(url) as response:
                    missing = json.load(response)
                self.assertIsNone(missing["source"])
                self.assertEqual(missing["sourceError"], "PDF no longer available")
                self.assertTrue(missing["versions"][0]["sections"]["methods"])
            finally:
                http.shutdown()
                http.server_close()
                worker.join()


if __name__ == "__main__":
    unittest.main()
