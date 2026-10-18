"""Preserve private notes, reject stale writes, and exercise HTTP without models."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import notes


class NotesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name) / 'notes'

    def test_each_template_persists_and_metadata_comes_from_paper(self):
        paper = {'key': 'PAPER', 'title': 'Original source', 'creators': ['Author'], 'doi': '10.1/test'}
        for template in notes.TEMPLATES:
            note = notes.create(self.directory, {'template': template['id'], 'paper': {'title': 'Spoofed'}}, paper)
            self.assertEqual(notes.load(self.directory, note['id']), note)
            self.assertEqual(note['paper']['title'], 'Original source')
            self.assertEqual(note['body'], template['body'])
        self.assertEqual(notes.listing(self.directory)['total'], 4)

    def test_parallel_updates_cannot_silently_overwrite_each_other(self):
        original = notes.create(self.directory, {'template': 'blank'})
        barrier = threading.Barrier(2)
        def edit(title):
            barrier.wait()
            try:
                return notes.update(self.directory, original['id'], {'revision': 1, 'title': title, 'body': title})
            except notes.Conflict:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(edit, ['Window A', 'Window B']))
        self.assertEqual(sum(value is not None for value in results), 1)
        saved = notes.load(self.directory, original['id'])
        self.assertEqual(saved['revision'], 2)
        self.assertEqual(saved, next(value for value in results if value))

    def test_search_by_body_and_filter_by_paper(self):
        first = notes.create(self.directory, {'template': 'blank'}, {'key': 'PAPER', 'title': '日冕仪'})
        notes.update(self.directory, first['id'], {'title': '理解', 'body': 'coherent wavefront', 'revision': 1})
        notes.create(self.directory, {'template': 'quick'})
        self.assertEqual(notes.listing(self.directory, 'WAVEFRONT')['total'], 1)
        self.assertEqual(notes.listing(self.directory, '日冕仪', 'PAPER')['total'], 1)
        self.assertEqual(notes.listing(self.directory, '', 'OTHER')['total'], 0)

    def test_invalid_requests_leave_saved_content_unchanged(self):
        note = notes.create(self.directory, {})
        for payload in [[], {}, {'title': '', 'body': 'x', 'revision': 1}, {'title': 'x', 'body': 'x' * 200001, 'revision': 1}, {'title': 'x', 'body': 'x', 'revision': True}]:
            with self.assertRaises(ValueError):
                notes.update(self.directory, note['id'], payload)
        self.assertEqual(notes.load(self.directory, note['id']), note)
        with self.assertRaises(ValueError):
            notes.load(self.directory, '../settings')
        with self.assertRaises(ValueError):
            notes.create(self.directory, {'template': 'unknown'})

    def test_corrupt_file_is_reported_without_destruction(self):
        note = notes.create(self.directory, {})
        path = self.directory / (note['id'] + '.json')
        path.write_text('{broken', encoding='utf-8')
        self.assertEqual(notes.listing(self.directory)['unreadable'], 1)
        with self.assertRaises(ValueError):
            notes.update(self.directory, note['id'], {'title': 'x', 'body': 'x', 'revision': 1})
        self.assertEqual(path.read_text(encoding='utf-8'), '{broken')

    def test_delete_removes_only_target_and_late_save_cannot_recreate_it(self):
        target = notes.create(self.directory, {'template': 'blank'})
        other = notes.create(self.directory, {})
        result = notes.delete(self.directory, target['id'], {'revision': target['revision']})
        self.assertEqual(result, {'deleted': True, 'id': target['id']})
        self.assertEqual(notes.listing(self.directory)['total'], 1)
        self.assertEqual(notes.load(self.directory, other['id']), other)
        with self.assertRaises(FileNotFoundError):
            notes.update(self.directory, target['id'], {'title': 'Late save', 'body': 'Draft', 'revision': 1})
        with self.assertRaises(FileNotFoundError):
            notes.delete(self.directory, target['id'], {'revision': 1})
        self.assertFalse(notes.path_for(self.directory, target['id']).exists())

    def test_stale_or_invalid_delete_preserves_latest_note(self):
        original = notes.create(self.directory, {})
        saved = notes.update(self.directory, original['id'], {'title': 'Another window', 'body': 'Keep me', 'revision': 1})
        with self.assertRaises(notes.Conflict):
            notes.delete(self.directory, saved['id'], {'revision': 1})
        for payload in [None, [], {}, {'revision': True}, {'revision': '2'}]:
            with self.assertRaises(ValueError):
                notes.delete(self.directory, saved['id'], payload)
        self.assertEqual(notes.load(self.directory, saved['id']), saved)

    def test_api_create_save_conflict_and_missing_library_without_models(self):
        spec = importlib.util.spec_from_file_location('reviewer_notes_http', Path(__file__).resolve().parents[1] / 'scripts/server.py')
        server_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server_module)
        store = Mock()
        store.item.return_value = {'key': 'PAPER', 'title': 'Paper', 'creators': []}
        with patch.object(server_module, 'NOTES_DIR', self.directory), patch.object(server_module, 'STORE', store), patch.object(server_module, 'model_config', side_effect=AssertionError('Notes must never use a model')):
            server = ThreadingHTTPServer(('127.0.0.1', 0), server_module.Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            def request(path, payload=None):
                req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}{path}', data=json.dumps(payload).encode() if payload is not None else None, headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(req) as response:
                    return json.load(response)
            try:
                created = request('/api/notes', {'template':'paper', 'itemKey':'PAPER'})
                saved = request('/api/notes/' + created['id'], {'title':'My note', 'body':'Keep this', 'revision':1})
                self.assertEqual(saved['revision'], 2)
                with self.assertRaises(urllib.error.HTTPError) as conflict:
                    request('/api/notes/' + created['id'], {'title':'Stale', 'body':'Wrong', 'revision':1})
                self.assertEqual(conflict.exception.code, 409)
                self.assertEqual(request('/api/notes/' + created['id'])['body'], 'Keep this')
                delete_path = '/api/notes/' + created['id'] + '/delete'
                with self.assertRaises(urllib.error.HTTPError) as stale_delete:
                    request(delete_path, {'revision': 1})
                self.assertEqual(stale_delete.exception.code, 409)
                with patch.object(server_module, 'STORE', None):
                    self.assertEqual(len(request('/api/note-templates')['templates']), 4)
                    self.assertEqual(request('/api/notes')['total'], 1)
                    self.assertIsNone(request('/api/notes', {'template':'blank'})['paper'])
                    self.assertTrue(request(delete_path, {'revision': 2})['deleted'])
                    self.assertEqual(request('/api/notes')['total'], 1)
                    with self.assertRaises(urllib.error.HTTPError) as missing:
                        request('/api/notes/' + created['id'])
                    self.assertEqual(missing.exception.code, 404)
                    with self.assertRaises(urllib.error.HTTPError) as missing_delete:
                        request(delete_path, {'revision': 2})
                    self.assertEqual(missing_delete.exception.code, 404)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
