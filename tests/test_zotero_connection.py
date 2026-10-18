"""Real temporary WAL files: isolate website reads from Zotero's exclusive lock."""
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('reviewer_connections',Path(__file__).resolve().parents[1]/'scripts/server.py')
reviewer=importlib.util.module_from_spec(spec);spec.loader.exec_module(reviewer)

class ZoteroConnectionTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        self.path=Path(directory.name)/'Library # one.sqlite'
        conn=sqlite3.connect(self.path)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('CREATE TABLE sample(value INTEGER)')
        conn.execute('INSERT INTO sample VALUES (1)');conn.commit();conn.close()
        self.store=reviewer.ZoteroStore.__new__(reviewer.ZoteroStore)
        self.store.db_path=self.path

    def assert_exclusive_available(self):
        conn=sqlite3.connect(self.path,timeout=.1)
        try:
            conn.execute('PRAGMA locking_mode=EXCLUSIVE')
            conn.execute('BEGIN EXCLUSIVE');conn.rollback()
        finally:conn.close()

    def test_website_reader_does_not_block_exclusive_startup(self):
        writer=sqlite3.connect(self.path,timeout=.1)
        try:
            with self.store.connect() as reader:
                self.assertEqual(reader.execute('SELECT value FROM sample').fetchone()[0],1)
                writer.execute('PRAGMA locking_mode=EXCLUSIVE')
                writer.execute('BEGIN EXCLUSIVE');writer.rollback()
            with self.assertRaises(sqlite3.ProgrammingError):reader.execute('SELECT 1')
            writer.execute('BEGIN EXCLUSIVE');writer.rollback()
        finally:writer.close()

    def test_context_closes_on_query_error_and_request_cancellation(self):
        for error in (ValueError('request cancelled'),sqlite3.OperationalError('no such table: missing')):
            with self.assertRaises(type(error)):
                with self.store.connect() as reader:
                    reader.execute('SELECT value FROM sample').fetchall()
                    raise error
            with self.assertRaises(sqlite3.ProgrammingError):reader.execute('SELECT 1')
            self.assert_exclusive_available()

    def test_new_reads_include_committed_wal_data_and_never_write(self):
        writer=sqlite3.connect(self.path)
        try:
            # Keep the writer open so the latest value stays in the WAL.
            writer.execute('UPDATE sample SET value=2');writer.commit()
            with self.store.connect() as reader:
                self.assertEqual(reader.execute('SELECT value FROM sample').fetchone()[0],2)
                with self.assertRaises(sqlite3.OperationalError):reader.execute('INSERT INTO sample VALUES (3)')
            self.assertEqual(writer.execute('SELECT COUNT(*) FROM sample').fetchone()[0],1)
        finally:writer.close()
        self.assert_exclusive_available()

    def test_reads_committed_wal_under_zotero_exclusive_lock(self):
        writer=sqlite3.connect(self.path,timeout=.1)
        writer.execute('PRAGMA locking_mode=EXCLUSIVE')
        writer.execute('UPDATE sample SET value=42');writer.commit()
        try:
            with self.store.connect() as reader:
                self.assertEqual(reader.execute('SELECT value FROM sample').fetchone()[0],42)
            # Uncommitted changes must remain invisible to the website.
            writer.execute('UPDATE sample SET value=99')
            with self.store.connect() as reader:
                self.assertEqual(reader.execute('SELECT value FROM sample').fetchone()[0],42)
        finally:writer.rollback();writer.close()
        self.assert_exclusive_available()

    def test_connection_and_temporary_files_removed_after_query(self):
        with self.store.connect() as reader:
            location=Path(reader.execute('PRAGMA database_list').fetchone()[2])
            self.assertNotEqual(location,self.path)
            self.assertTrue(location.exists())
        self.assertFalse(location.parent.parent.exists())
        with self.assertRaises(sqlite3.ProgrammingError):reader.execute('SELECT 1')

    def test_changing_source_retries_and_never_serves_unverified_data(self):
        snapshot=reviewer.zotero_snapshot
        real_digest=snapshot._digest
        calls=[]
        def changed_once(path):
            calls.append(path)
            return b'changed' if len(calls)==1 else real_digest(path)
        with patch.object(snapshot,'_digest',side_effect=changed_once):
            with self.store.connect() as reader:
                self.assertEqual(reader.execute('SELECT value FROM sample').fetchone()[0],1)
        self.assertGreaterEqual(len(calls),2)
        with patch.object(snapshot,'_digest',return_value=b'always changing'):
            with self.assertRaisesRegex(RuntimeError,'暂未取得可验证的副本'):
                with self.store.connect():self.fail('unstable copy must not be used')

    def test_corrupt_database_and_active_rollback_journal_are_rejected(self):
        self.path.write_bytes(b'not a database')
        with self.assertRaisesRegex(RuntimeError,'暂未取得可验证的副本'):
            with self.store.connect():self.fail('corrupt copy must not be used')
        Path(str(self.path)+'-journal').write_bytes(b'active journal')
        with self.assertRaisesRegex(RuntimeError,'暂未取得可验证的副本'):
            with self.store.connect():self.fail('rollback transaction must not be copied')

    def test_original_files_are_unchanged_by_website_queries(self):
        writer=sqlite3.connect(self.path)
        try:
            writer.execute('UPDATE sample SET value=7');writer.commit()
            paths=[self.path,Path(str(self.path)+'-wal'),Path(str(self.path)+'-shm')]
            before={p:p.read_bytes() for p in paths}
            with self.store.connect() as reader:
                reader.execute('SELECT * FROM sample').fetchall()
            self.assertEqual(before,{p:p.read_bytes() for p in paths})
        finally:writer.close()

if __name__=='__main__':unittest.main()
