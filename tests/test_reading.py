"""Journal identity and reading priority; no paid model calls."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("reviewer_reading", Path(__file__).resolve().parents[1] / "scripts/server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
jm, rp = server.journal_metrics, server.reading_priority


def catalog(cas=(), jcr=()):
    db = jm.Catalog.__new__(jm.Catalog)
    db.rows = {"cas": [], "jcr": []}
    db.index = {kind: {"issn": {}, "title": {}} for kind in db.rows}
    db.errors = []
    db.add_rows("cas", cas)
    db.add_rows("jcr", jcr)
    return db


class JournalTests(unittest.TestCase):
    def test_issn_identity_conflicts_and_unmatched_prevent_title_fallback(self):
        db = catalog(cas=[{"Journal": "The Astrophysical Journal", "ISSN/EISSN": "0004-637X"}, {"Journal": "Astrophysical Journal Letters", "ISSN/EISSN": "2041-8205"}])
        result = db.lookup({"issn": "2041-8205", "publicationTitle": "The Astrophysical Journal"})
        self.assertEqual(result["cas"]["journal"], "Astrophysical Journal Letters")
        self.assertEqual(result["cas"]["match"], "issn")
        self.assertEqual(db.lookup({"issn": "0004-637X / 2041-8205"})["status"], "ambiguous")
        self.assertEqual(db.lookup({"issn": "9999-9999", "publicationTitle": "The Astrophysical Journal"})["status"], "issn_unmatched")
        self.assertIsNone(db.lookup({"publicationTitle": "Astrophysical"})["cas"])

    def test_multi_subject_divisions_quartiles_and_year_survive(self):
        db = catalog(cas=[{"Journal": "Test Journal", "大类": "工程", "大类分区": "4 [125/300]", "小类1": "光学", "小类1分区": "3 [20/40]"}], jcr=[{"Journal": "TEST JOURNAL", "IF(2025)": "6.8", "Category_1": "OPTICS", "IF Quartile(2025)_1": "Q1", "Category_2": "ENGINEERING", "IF Quartile(2025)_2": "Q3"}])
        result = db.lookup({"publicationTitle": "The Test Journal", "date": "1998"})
        self.assertEqual(result["cas"]["division"], 4)
        self.assertEqual(result["cas"]["subjects"][0]["division"], 3)
        self.assertEqual(result["jcr"]["impactFactor"], 6.8)
        self.assertEqual(result["jcr"]["year"], 2025)
        self.assertEqual([s["quartile"] for s in result["jcr"]["subjects"]], ["Q1", "Q3"])

    def test_ambiguity_nonjournal_missing_and_tampering(self):
        db = catalog(jcr=[{"Journal": "Test-Journal"}, {"Journal": "Test Journal"}])
        self.assertEqual(db.lookup({"publicationTitle": "TEST JOURNAL"})["status"], "ambiguous")
        self.assertEqual(db.lookup({"itemType": "conferencePaper", "publicationTitle": "Test Journal"})["status"], "not_applicable")
        self.assertEqual(db.lookup({"publicationTitle": "arXiv"})["status"], "not_applicable")
        self.assertIsNone(db.lookup({"publicationTitle": "Unknown"})["jcr"])
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / jm.MANIFEST["files"][0]["name"]).write_text("fake", encoding="utf-8")
            db = jm.Catalog(directory)
            self.assertFalse(db.status()["ready"])
            self.assertEqual(db.lookup({"publicationTitle": "Unknown"})["status"], "data_unavailable")

    def test_division_requires_actual_cas_or_jcr_quartile(self):
        self.assertTrue(jm.has_division({"cas": {"division": 2}}))
        self.assertTrue(jm.has_division({"cas": {"subjects": [{"division": 3}]}}))
        self.assertTrue(jm.has_division({"jcr": {"subjects": [{"quartile": "Q4"}]}}))
        for metrics in (None, {}, {"status": "matched"}, {"jcr": {"impactFactor": 11}}, {"cas": {"division": None}}, {"jcr": {"subjects": [{"quartile": "N/A"}]}}):
            self.assertFalse(jm.has_division(metrics))


class PriorityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        for name, value in (("CACHE_DIR", self.directory / "priority"), ("PROFILE_PATH", self.directory / "research.json")):
            current = patch.object(rp, name, value)
            current.start()
            self.addCleanup(current.stop)
        self.item = {"key": "TEST", "title": "Adaptive optics and wavefront sensing", "abstract": "We test wavefront sensing with calibrated laboratory measurements."}
        rp.save_profile({"goal": "研究自适应光学的实验方法", "topics": "自适应光学 | adaptive optics\n波前感知 | wavefront sensing"})

    def evaluation(self, relevance=55, content=27):
        return {"relevance": relevance, "contentValue": content, "reason": "Directly applicable measured method", "evidence": [self.item["abstract"]]}

    def test_missing_journal_does_not_penalize_and_metrics_cannot_outweigh_relevance(self):
        result = rp.scored_result(self.evaluation(54, 27), {}, self.item["abstract"])
        self.assertEqual((result["tier"], result["score"], result["journalPoints"]), ("夯", 90, None))
        result = rp.scored_result(self.evaluation(10, 30), {"cas": {"division": 1}}, self.item["abstract"])
        self.assertEqual(result["tier"], "拉")
        self.assertLess(result["score"], 30)

    def test_evidence_must_be_real_and_insufficient_material_stays_unassessed(self):
        evaluation = self.evaluation()
        evaluation["evidence"] = ["This invented quotation does not occur in the paper"]
        result = rp.scored_result(evaluation, {}, self.item["abstract"])
        self.assertEqual(result["tier"], "待评估")
        self.assertIsNone(result["score"])
        self.assertEqual(result["evidenceVerification"], "unverified")
        self.assertEqual(rp.save_result(self.item, {}, result)["reason"], evaluation["reason"])
        self.assertTrue(rp.priority_for(self.item, {})["cached"])
        self.assertEqual(rp.scored_result({"relevance": None, "contentValue": None, "reason": "Insufficient source"}, {}, "Title only")["tier"], "待评估")

    def test_source_ids_resolve_to_original_excerpts_and_reject_unknown_ids(self):
        source = "Title: Test method\n\n[第 2 页]\n" + self.item["abstract"]
        fragments = rp.source_fragments(source)
        self.assertEqual(fragments[-1]["page"], 2)
        evaluation = {**self.evaluation(), "evidence": [], "evidenceIds": [fragments[-1]["id"]]}
        result = rp.scored_result(evaluation, {}, source, fragments)
        self.assertEqual(result["evidence"], [self.item["abstract"]])
        self.assertEqual(result["tier"], "夯")
        evaluation["evidenceIds"] = ["S999"]
        self.assertEqual(rp.scored_result(evaluation, {}, source, fragments)["tier"], "待评估")

    def test_pdf_typography_line_breaks_and_mixed_quote_formats(self):
        source = "The adap-\ntive optics method improves the efﬁciency of high-\ncontrast imaging."
        quote = "The adaptive optics method improves the efficiency of high-contrast imaging."
        result = rp.scored_result({**self.evaluation(), "evidence": [{"quote": quote, "page": 2}, "An invented sentence that should be discarded"]}, {}, source)
        self.assertEqual(result["evidence"], [quote])
        self.assertEqual(result["evidenceVerification"], "partial")
        self.assertEqual(result["tier"], "夯")
        self.assertEqual(rp.scored_result({**self.evaluation(), "evidence": quote.replace("improves", "does not improve")}, {}, source)["tier"], "待评估")

    def test_model_request_uses_paper_quotes_and_handles_nontext_response(self):
        store = Mock()
        store.analysis_context.return_value = (self.item, self.item["abstract"])
        config = {"configured": True, "model": "mock", "baseUrl": "https://model.invalid/v1", "apiKey": "mock-not-a-real-key"}
        def response(content):
            return io.BytesIO(json.dumps({"choices": [{"message": {"content": content}}]}).encode())
        with patch.object(server, "STORE", store), patch.object(server, "model_config", return_value=config):
            with patch.object(server.urllib.request, "urlopen", return_value=response(json.dumps({**self.evaluation(), "evidence": [], "evidenceIds": ["S001"]}))) as model:
                result = server.generate_priority(self.item, {}, rp.profile())
                self.assertEqual(result["tier"], "夯")
                request_body = json.loads(model.call_args.args[0].data)
                self.assertIn(self.item["abstract"], request_body["messages"][1]["content"])
                self.assertIn("[S001]", request_body["messages"][1]["content"])
            with patch.object(server.urllib.request, "urlopen", return_value=response(None)):
                with self.assertRaises(RuntimeError):
                    server.generate_priority(self.item, {}, rp.profile())

    def test_cache_reuse_and_goal_or_content_invalidation(self):
        saved = rp.save_result(self.item, {}, {"tier": "顶级", "score": 77, "method": "model", "reason": "Saved"})
        self.assertTrue(saved["cached"])
        self.assertEqual(rp.priority_for(self.item, {})["reason"], "Saved")
        self.assertEqual(rp.priority_for(self.item, {"summary": {"findings": "New evidence"}})["tier"], "待评估")
        old_profile = rp.profile()
        rp.save_profile({"goal": "A different experiment", "topics": "experiment"})
        current = rp.priority_for(self.item, {})
        self.assertTrue(current["stale"])
        self.assertEqual(current["tier"], "待评估")
        self.assertEqual(rp.priority_for(self.item, {}, old_profile)["tier"], "顶级")

    def test_keywords_are_only_signals_and_broken_cache_is_safe(self):
        current = rp.priority_for(self.item, {})
        self.assertIn("自适应光学", current["signals"])
        self.assertEqual(current["tier"], "待评估")
        self.assertEqual(rp.topic_signals({"title": "COADAPTIVE OPTICSAL"}, {}, {"topics": "adaptive optics"}), [])
        path = rp.cache_path(self.item, {}, rp.profile())
        path.parent.mkdir(parents=True)
        path.write_text("{broken", encoding="utf-8")
        self.assertEqual(rp.priority_for(self.item, {})["tier"], "待评估")

    def test_sort_and_tier_filter_precede_limit_without_model_calls(self):
        store = server.ZoteroStore.__new__(server.ZoteroStore)
        store.version = "test"
        store._all_items = Mock(return_value=[{"key": "A", "title": "Unknown"}, self.item])
        store._visible_collections = Mock(return_value=[])
        rp.save_result(self.item, {}, {"tier": "夯", "score": None, "method": "manual", "reason": "Important"})
        with patch.object(server, "load_analysis", return_value={}), patch.object(server, "generate_priority", side_effect=AssertionError("No paid requests")):
            self.assertEqual(store.library(sort="priority", limit=1)["items"][0]["key"], "TEST")
            self.assertEqual(store.library(tier="夯", limit=1)["matchingCount"], 1)

    def test_division_groups_counts_progress_and_limit_stay_consistent(self):
        store = server.ZoteroStore.__new__(server.ZoteroStore)
        store.version = "test"
        store._visible_collections = Mock(return_value=[])
        store._all_items = Mock(return_value=[{"key": "A", "title": "Other paper"}, {"key": "B", "title": "Relevant optics"}, {"key": "C", "title": "Relevant optics follow-up"}])
        db = Mock()
        db.lookup.side_effect = lambda item: {"cas": {"division": 1}} if item["key"] == "B" else {"jcr": {"impactFactor": 3}}
        db.status.return_value = {"ready": True}
        with patch.object(server.journal_metrics, "catalog", return_value=db), patch.object(server, "load_analysis", return_value={}), patch.object(server, "analysis_status", side_effect=lambda key: {"summary": key == "B", "terms": False, "figures": False}), patch.object(server, "generate_priority", side_effect=AssertionError("No model calls")):
            result = store.library(division="available", limit=1)
            self.assertEqual(result["divisionCounts"], {"all": 3, "available": 1, "unavailable": 2})
            self.assertEqual([i["key"] for i in result["items"]], ["B"])
            self.assertEqual(result["progress"]["summary"], 1)
            result = store.library(division="unavailable", limit=1)
            self.assertEqual(result["matchingCount"], 2)
            self.assertEqual(result["progress"]["total"], 2)
            self.assertEqual(store.library(query="Relevant", division="available")["divisionCounts"]["all"], 2)
            self.assertEqual(store.library(status="unread", division="available")["matchingCount"], 0)
            with self.assertRaises(ValueError):
                store.library(division="invalid")

    def test_http_evaluation_cache_manual_reset_and_stale_profile(self):
        store = Mock()
        store.item.return_value = self.item
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        worker = threading.Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        try:
            url = f"http://127.0.0.1:{httpd.server_port}/api/items/TEST/priority"
            def post(**values):
                body = {"profileVersion": rp.profile()["version"], **values}
                request = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request) as response:
                    return json.load(response)
            with patch.object(server, "STORE", store), patch.object(server, "load_analysis", return_value={}), patch.object(server, "generate_priority", return_value={"tier": "夯", "score": 90, "reason": "Mocked evidence", "method": "model"}) as generate:
                self.assertEqual(post(action="evaluate")["tier"], "夯")
                self.assertTrue(post(action="evaluate")["cached"])
                self.assertEqual(generate.call_count, 1)
                self.assertEqual(post(action="manual", tier="NPC", reason="Later")["tier"], "NPC")
                self.assertEqual(generate.call_count, 1)
                self.assertEqual(post(action="reset")["tier"], "待评估")
                with self.assertRaises(urllib.error.HTTPError) as error:
                    post(action="evaluate", profileVersion="stale")
                self.assertEqual(error.exception.code, 400)
                self.assertEqual(generate.call_count, 1)
                generate.return_value = rp.scored_result({**self.evaluation(), "evidence": ["A fabricated quote unrelated to the actual paper"]}, {}, self.item["abstract"])
                self.assertEqual(post(action="evaluate")["tier"], "待评估")
                self.assertEqual(post(action="evaluate")["evidenceVerification"], "unverified")
                self.assertEqual(generate.call_count, 2)
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
