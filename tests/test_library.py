"""Verify conservative display deduplication without modifying Zotero."""
import copy
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("reviewer_library", Path(__file__).resolve().parents[1] / "scripts/server.py")
reviewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reviewer)


def paper(key, **fields):
    return {"key": key, "title": "Methods and limitations of focal plane sensing", **fields}


class LibraryTests(unittest.TestCase):
    def collection_store(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        self.addCleanup(conn.close)
        conn.executescript("""
            CREATE TABLE collections (collectionID INTEGER, key TEXT, collectionName TEXT);
            CREATE TABLE deletedCollections (collectionID INTEGER);
            CREATE TABLE collectionItems (collectionID INTEGER, itemID INTEGER);
            INSERT INTO collections VALUES (1, 'ACTIVE', 'Current'), (2, 'DELETED', 'Translation'), (3, 'EMPTY', 'Empty collection');
            INSERT INTO deletedCollections VALUES (2);
            INSERT INTO collectionItems VALUES (1, 1), (2, 1);
        """)
        store = reviewer.ZoteroStore.__new__(reviewer.ZoteroStore)
        store.version = "test"
        store.connect = Mock(return_value=conn)
        store._all_items = Mock(return_value=[paper("READ", doi="10.1234/a", collections=[{"key": "ACTIVE"}]), paper("UNREAD", doi="10.1234/b")])
        return store, conn

    def test_deleted_collections_disappear_but_empty_collections_remain(self):
        store, conn = self.collection_store()
        self.assertEqual([c["key"] for c in store.collections()], ["ACTIVE", "EMPTY"])
        self.assertEqual([c["key"] for c in store._collections(conn, 1)], ["ACTIVE"])
        with tempfile.TemporaryDirectory() as directory, patch.object(reviewer, "ANALYSIS_DIR", Path(directory)):
            result = store.library(collection="DELETED")
            self.assertEqual(result["collection"], "")
            self.assertEqual(result["progress"]["total"], 2)
            empty = store.library(collection="EMPTY")
            self.assertEqual(empty["collection"], "EMPTY")
            self.assertEqual(empty["progress"]["total"], 0)

    def test_progress_uses_saved_results_and_filtering_precedes_limit(self):
        store, _ = self.collection_store()
        with tempfile.TemporaryDirectory() as directory, patch.object(reviewer, "ANALYSIS_DIR", Path(directory)), patch.object(reviewer, "generate_summary", side_effect=AssertionError("No model calls")):
            reviewer.save_analysis("READ", "summary", {"summary": {"findings": "Saved"}})
            reviewer.save_analysis("READ", "terms", {"terms": [{"term": "Saved term"}]})
            reviewer.save_figure("READ", "PDF:1", {"figure": {"description": "Saved figure"}})
            result = store.library(limit=1)
            self.assertEqual(result["progress"], {"total": 2, "summary": 1, "unread": 1, "terms": 1, "figures": 1})
            self.assertEqual(result["matchingCount"], 2)
            self.assertEqual(len(result["items"]), 1)
            for kind in ("summary", "terms", "figures"):
                self.assertEqual([i["key"] for i in store.library(status=kind)["items"]], ["READ"])
            self.assertEqual([i["key"] for i in store.library(status="unread", limit=1)["items"]], ["UNREAD"])
            self.assertEqual(store.library(collection="ACTIVE")["progress"]["total"], 1)
            self.assertEqual(store.library(query="no such title")["progress"]["total"], 0)
            reviewer.save_analysis("UNREAD", "summary", {"summary": {"findings": "New saved result"}})
            self.assertEqual(store.library()["progress"]["summary"], 2)

    def test_missing_empty_or_broken_cache_is_not_marked_complete(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(reviewer, "ANALYSIS_DIR", Path(directory)):
            self.assertFalse(reviewer.analysis_status("MISSING")["summary"])
            for value in ('{"summary":null,"terms":[],"figures":{}}', '{broken', '[]'):
                (Path(directory) / "EMPTY.json").write_text(value, encoding="utf-8")
                self.assertEqual(reviewer.analysis_status("EMPTY"), {"summary": False, "terms": False, "figures": False, "figureCount": 0})

    def test_zotero_trash_is_excluded_before_display_grouping(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript("""
                CREATE TABLE items (itemID INTEGER, key TEXT, itemTypeID INTEGER, dateModified TEXT);
                CREATE TABLE itemTypes (itemTypeID INTEGER, typeName TEXT);
                CREATE TABLE deletedItems (itemID INTEGER);
                INSERT INTO itemTypes VALUES (2, 'journalArticle');
                INSERT INTO items VALUES (1, 'PDF', 2, '2026-01-01'), (2, 'TRASH', 2, '2026-01-02');
                INSERT INTO deletedItems VALUES (2);
            """)
            store = reviewer.ZoteroStore.__new__(reviewer.ZoteroStore)
            store.connect = Mock(return_value=conn)
            store._item = Mock(side_effect=lambda db, row: paper(row["key"]))
            self.assertEqual([i["key"] for i in store.items()], ["PDF"])
        finally:
            conn.close()

    def test_publisher_snapshot_resolves_to_existing_pdf(self):
        items = [
            paper("HTML", url="https://publisher.test/10.1117/1.JATIS.2.1.011009.full", attachments=[{"filename": "page.html", "exists": True}]),
            paper("MISSING", doi="10.1117/1.JATIS.2.1.011009", attachments=[{"filename": "paper.pdf", "exists": False}]),
            paper("PDF", doi="https://doi.org/10.1117/1.JATIS.2.1.011009", attachments=[{"contentType": "application/pdf", "exists": True}]),
        ]
        original = copy.deepcopy(items)
        result = reviewer.visible_papers(reviewer.paper_groups(items))
        self.assertEqual([i["key"] for i in result], ["PDF"])
        self.assertEqual(items, original)

    def test_punctuation_and_case_title_alias_matches(self):
        items = [paper("HTML", title="Review of high-contrast imaging systems I: Methods"), paper("PDF", title="Review of high-contrast imaging systems I. methods", doi="10.1234/paper", attachments=[{"filename": "paper.PDF", "exists": True}])]
        self.assertEqual(reviewer.visible_papers(reviewer.paper_groups(items))[0]["key"], "PDF")
        self.assertEqual(len(reviewer.paper_groups(items)), 1)

    def test_conflicting_dois_and_ambiguous_unlabelled_title_stay_separate(self):
        items = [paper("A", doi="10.1234/one"), paper("UNKNOWN"), paper("B", doi="10.1234/two")]
        self.assertEqual(len(reviewer.paper_groups(items)), 3)
        self.assertEqual(len(reviewer.paper_groups(list(reversed(items)))), 3)

    def test_series_parts_and_unnamed_entries_stay_separate(self):
        items = [paper("I", title="Review of high contrast imaging systems I"), paper("II", title="Review of high contrast imaging systems II"), paper("X", title="未命名条目"), paper("Y", title="未命名条目")]
        self.assertEqual(len(reviewer.paper_groups(items)), 4)

    def test_alias_search_collection_and_limit_apply_after_grouping(self):
        items = [
            paper("HTML", title="中文译名用于搜索", url="https://publisher.test/10.1234/paper.full", collections=[{"key": "C"}]),
            paper("PDF", doi="10.1234/paper", attachments=[{"filename": "paper.pdf", "exists": True}]),
            paper("OTHER", title="A completely different and unrelated scientific paper"),
        ]
        groups = reviewer.paper_groups(items)
        self.assertEqual([i["key"] for i in reviewer.visible_papers(groups, "中文", "C")], ["PDF"])
        self.assertEqual([i["key"] for i in reviewer.visible_papers(groups, limit=2)], ["PDF", "OTHER"])
        self.assertEqual(reviewer.visible_papers(groups, collection="NONEXISTENT"), [])


if __name__ == "__main__":
    unittest.main()
