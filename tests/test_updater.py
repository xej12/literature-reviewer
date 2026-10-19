"""Exercise real file transactions and launcher recovery without GitHub/model calls."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
import zipfile

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
spec = importlib.util.spec_from_file_location('tested_updater', SCRIPTS / 'updater.py')
updates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updates)

FAKE_SERVER = '''import json, os, pathlib, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
root = pathlib.Path(__file__).resolve().parents[1]
exiting = [0]
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        value = {'app':'literature-reviewer', 'version':json.loads((root/'version.json').read_text())['version'], 'instanceId':os.environ.get('LITERATURE_REVIEWER_INSTANCE')}
        body=json.dumps(value).encode(); self.send_response(200); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length','0')))
        self.send_response(200); self.send_header('Content-Length','2'); self.end_headers(); self.wfile.write(b'{}')
        exiting[0]=75 if self.path=='/handoff' else 0
        threading.Thread(target=server.shutdown).start()
server=ThreadingHTTPServer(('127.0.0.1',int(sys.argv[1])),Handler)
server.serve_forever(); server.server_close(); sys.exit(exiting[0])
'''


def fixture(root, version='1.0.0', broken=False):
    files = {'version.json': json.dumps({'version': version, 'updateFormat': 1}).encode(),
             'scripts/server.py': b'import sys; sys.exit(17)' if broken else FAKE_SERVER.encode(),
             'scripts/launch.py': (SCRIPTS / 'launch.py').read_bytes(),
             'scripts/updater.py': (SCRIPTS / 'updater.py').read_bytes(),
             'web/index.html': ('version ' + version).encode(),
             'requirements.txt': b'Pillow>=10.0\n', 'vendor/poppler/manifest.json': b'{"version":"26.09.0-0"}',
             'scripts/obsolete.py' if version == '1.0.0' else 'scripts/new.py': b'# program file\n'}
    for name, content in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    manifest = {'format': 1, 'version': version, 'files': {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}}
    updates.write_json(root / updates.MANIFEST, manifest)
    return manifest


def package(root):
    stream = io.BytesIO()
    manifest = updates.read_json(root / updates.MANIFEST)
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in [*manifest['files'], updates.MANIFEST]: archive.write(root / name, 'literature-reviewer/' + name)
    return stream.getvalue()


def personal(root):
    values = {'data/settings.json': b'{"apiKey":"never-upload"}', 'data/notes/note.json': b'private notes',
              'data/cards/card.json': b'private cards', '.venv/Lib/site-packages/marker': b'dependencies',
              'vendor/poppler/runtime/Library/bin/pdfinfo.exe': b'existing runtime', '.env': b'custom setting',
              'my-file.txt': b'personal extra file'}
    for name, content in values.items():
        target = root / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(content)
    return values


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'installed'; self.root.mkdir()
        self.old = fixture(self.root)
        self.personal = personal(self.root)
        self.plan = {'id': 'a' * 32, 'version': '2.0.0'}
        self.work = updates.work_directory(self.root, self.plan['id'])
        self.new = self.work / 'new'
        self.new_manifest = fixture(self.new, '2.0.0')
        updates.write_json(self.root / '.updates/plan.json', self.plan)

    def tearDown(self): self.temp.cleanup()

    def assert_private_unchanged(self):
        for name, content in self.personal.items(): self.assertEqual((self.root / name).read_bytes(), content, name)

    def test_update_and_rollback_preserve_all_personal_files(self):
        updates.apply_update(self.root, self.plan)
        self.assertEqual(updates.current_version(self.root), '2.0.0')
        self.assertFalse((self.root / 'scripts/obsolete.py').exists())
        self.assertTrue((self.root / 'scripts/new.py').is_file())
        self.assert_private_unchanged()
        updates.rollback(self.root, self.plan)
        self.assertEqual(updates.current_version(self.root), '1.0.0')
        self.assertTrue((self.root / 'scripts/obsolete.py').is_file())
        self.assertFalse((self.root / 'scripts/new.py').exists())
        self.assertEqual(updates.read_json(self.root / updates.MANIFEST), self.old)
        self.assert_private_unchanged()

    def test_partial_replacement_error_restores_old_program(self):
        original = updates.os.replace
        def denied(source, target):
            if str(target).endswith('version.json'): raise PermissionError('simulated locked program file')
            return original(source, target)
        with patch.object(updates.os, 'replace', side_effect=denied):
            with self.assertRaises(PermissionError): updates.apply_update(self.root, self.plan)
        self.assertEqual(updates.current_version(self.root), '1.0.0')
        for name, digest in self.old['files'].items(): self.assertEqual(updates.sha256(self.root / name), digest)
        self.assertFalse((self.root / 'scripts/new.py').exists())
        self.assert_private_unchanged()

    def test_user_code_edits_and_new_dependency_require_manual_upgrade(self):
        (self.root / 'web/index.html').write_text('user edits')
        with self.assertRaisesRegex(ValueError, '修改'): updates.validate_installation(self.root, self.new)
        (self.root / 'web/index.html').write_bytes(b'version 1.0.0')
        (self.new / 'requirements.txt').write_text('new-dependency')
        self.new_manifest['files']['requirements.txt'] = updates.sha256(self.new / 'requirements.txt')
        updates.write_json(self.new / updates.MANIFEST, self.new_manifest)
        with self.assertRaisesRegex(ValueError, '依赖'): updates.validate_installation(self.root, self.new)
        self.assert_private_unchanged()

    def test_source_checkout_is_never_overwritten(self):
        (self.root / '.git').mkdir()
        manager = updates.Updater(self.root, supervised=True)
        self.assertFalse(manager.status()['supported'])
        with self.assertRaisesRegex(ValueError, 'Git'): updates.validate_installation(self.root, self.new)

    def test_active_write_prevents_update_and_new_writes_wait_during_update(self):
        manager = updates.Updater(self.root, supervised=True)
        manager.release = {'version': '2.0.0', 'url': updates.RELEASE_URL, 'notes': '', 'assets': [{'size': 100}]}
        manager.on_ready = lambda: None
        with manager.mutation():
            with self.assertRaises(updates.Busy): manager.start('2.0.0')
        manager.local_busy = True
        with self.assertRaises(updates.Busy):
            with manager.mutation(): self.fail('should not write during update')

    def test_failed_checksum_keeps_original_code_and_never_stops_service(self):
        manager = updates.Updater(self.root, supervised=True)
        release = {'version': '2.0.0', 'url': updates.RELEASE_URL, 'notes': '',
                   'assets': [{'url':'package', 'size':3}, {'url':'checksum'}]}
        manager.release = release
        called = []
        manager.on_ready = lambda: called.append(True)
        def fetch(url, limit, progress=None, output=None):
            if output: Path(output).write_bytes(b'bad'); return b''
            return (('0' * 64) + '  ' + updates.PACKAGE).encode()
        with patch.object(updates, 'latest_release', return_value=release), patch.object(updates, 'fetch', side_effect=fetch):
            manager.start('2.0.0')
            deadline = time.monotonic() + 5
            while manager.local_busy and time.monotonic() < deadline: time.sleep(.01)
        self.assertFalse(called)
        self.assertFalse(manager.local_busy)
        self.assertEqual(manager.status()['operation']['phase'], 'failed')
        self.assertEqual(updates.current_version(self.root), '1.0.0')
        self.assert_private_unchanged()

    def test_interrupted_install_can_be_restored_using_persisted_journal(self):
        updates.apply_update(self.root, self.plan)
        # Recovery uses only persisted files, as after a Windows restart.
        restored = updates.read_json(self.root / '.updates/plan.json')
        updates.rollback(self.root, restored)
        self.assertEqual(updates.current_version(self.root), '1.0.0')
        self.assert_private_unchanged()


class ArchiveTests(unittest.TestCase):
    def test_private_paths_windows_aliases_and_traversal_are_rejected(self):
        for name in ['../data/settings.json', '/scripts/a.py', 'scripts/../a.py', 'scripts\\a.py',
                     'data/settings.json', '.venv/a', '.updates/status.json', 'scripts/AUX.txt',
                     'scripts/a.py:stream', 'scripts/a. /file', 'vendor/poppler/runtime/x.exe']:
            with self.subTest(name=name), self.assertRaises(ValueError): updates.managed_path(name)

    def test_verified_archive_extracts_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root / 'source', '2.0.0')
            content = package(root / 'source')
            archive = root / 'release.zip'; archive.write_bytes(content)
            updates.extract_verified(archive, root / 'new', '2.0.0')
            self.assertEqual(updates.current_version(root / 'new'), '2.0.0')
            changed = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(content)) as old, zipfile.ZipFile(changed, 'w') as target:
                for info in old.infolist(): target.writestr(info, b'corrupt' if info.filename.endswith('/scripts/server.py') else old.read(info))
            archive.write_bytes(changed.getvalue())
            with self.assertRaisesRegex(ValueError, '校验失败'): updates.extract_verified(archive, root / 'bad', '2.0.0')

    def test_duplicate_case_and_injected_private_file_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root / 'source', '2.0.0')
            for injected in ['literature-reviewer/scripts/SERVER.py', 'literature-reviewer/data/settings.json']:
                content = io.BytesIO(package(root / 'source'))
                with zipfile.ZipFile(content, 'a') as target: target.writestr(injected, b'bad')
                path = root / 'bad.zip'; path.write_bytes(content.getvalue())
                with self.assertRaises(ValueError): updates.extract_verified(path, root / 'bad', '2.0.0')

    def test_versions_use_numeric_comparison_and_reject_prereleases(self):
        self.assertGreater(updates.version('v0.10.0'), updates.version('v0.9.9'))
        for value in ['main', '1.2', 'v1.2.3-beta', '01.2.3']:
            with self.assertRaises(ValueError): updates.version(value)

    def test_other_repository_asset_is_rejected(self):
        value = {'tag_name':'v2.0.0', 'assets':[{'name':updates.PACKAGE, 'state':'uploaded', 'size':100,
                 'browser_download_url':'https://github.com/someone/other/releases/download/v2.0.0/' + updates.PACKAGE}]}
        with patch.object(updates, 'fetch', return_value=json.dumps(value).encode()), self.assertRaises(ValueError): updates.latest_release()

    def test_api_limit_falls_back_to_official_stable_release_page(self):
        with patch.object(updates, 'fetch', side_effect=[updates.GitHubLimited('rate limited'),
                          (b'public release page', 'https://github.com/xej12/literature-reviewer/releases/tag/v2.0.0')]):
            value = updates.latest_release()
        self.assertEqual(value['version'], '2.0.0')
        self.assertEqual(value['assets'][0]['url'], 'https://github.com/xej12/literature-reviewer/releases/download/v2.0.0/' + updates.PACKAGE)

    def test_automatic_checks_are_cached_without_calling_model_or_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root)
            release = {'version':'2.0.0', 'url':updates.RELEASE_URL, 'notes':'new version', 'assets':[]}
            updates.write_json(root / '.updates/check.json', {'checkedAt':time.time(), 'release':release})
            manager = updates.Updater(root)
            with patch.object(updates, 'latest_release', side_effect=AssertionError('unexpected network')):
                result = manager.check()
            self.assertTrue(result['available'])
            self.assertFalse(result['checking'])

    def test_release_builder_emits_complete_manifest(self):
        build_spec = importlib.util.spec_from_file_location('release_builder_test', SCRIPTS / 'build-release.py')
        builder = importlib.util.module_from_spec(build_spec)
        build_spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root / 'source')
            with zipfile.ZipFile(root / 'poppler.zip', 'w') as binary:
                binary.writestr('Library/bin/pdfinfo.exe', b'fixture')
                binary.writestr('Library/bin/pdftoppm.exe', b'fixture')
            poppler_digest = updates.sha256(root / 'poppler.zip')
            (root / 'source/vendor/poppler/manifest.json').write_text(json.dumps({'sha256':poppler_digest}))
            source = io.BytesIO()
            with zipfile.ZipFile(source, 'w') as archive:
                for path in (root / 'source').rglob('*'):
                    if path.is_file() and path.name != updates.MANIFEST: archive.write(path, path.relative_to(root / 'source').as_posix())
            with patch.object(builder.subprocess, 'check_output', return_value=source.getvalue()):
                checksum = builder.build(root / 'poppler.zip', root / 'output.zip')
            self.assertEqual(checksum.read_text().split()[0], updates.sha256(root / 'output.zip'))
            files = updates.extract_verified(root / 'output.zip', root / 'unpacked', '1.0.0')
            self.assertEqual(files['vendor/poppler/windows-x64.zip'], poppler_digest)


class UpdateAPITests(unittest.TestCase):
    def test_updates_require_local_origin_and_secret_and_busy_blocks_writes(self):
        api_spec = importlib.util.spec_from_file_location('updater_api_server', SCRIPTS / 'server.py')
        api = importlib.util.module_from_spec(api_spec)
        api_spec.loader.exec_module(api)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); fixture(root)
            manager = updates.Updater(root, supervised=True)
            # Handler catches its imported updater.Busy class.
            api.updater = updates
            api.UPDATES = manager
            from http.server import ThreadingHTTPServer
            http = ThreadingHTTPServer(('127.0.0.1',0), api.Handler)
            thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
            base = f'http://127.0.0.1:{http.server_port}'
            def post(path, headers=None):
                request = urllib.request.Request(base + path, data=b'{}', headers={'Content-Type':'application/json', **(headers or {})})
                try:
                    with urllib.request.urlopen(request, timeout=3) as response: return response.status, json.loads(response.read())
                except urllib.error.HTTPError as error: return error.code, json.loads(error.read())
            try:
                self.assertEqual(post('/api/update/check')[0], 403)
                self.assertEqual(post('/api/update/check', {'X-Update-Token':manager.token,'Origin':'https://other.example'})[0], 403)
                with patch.object(manager, 'check', return_value={'checking':True}) as checked:
                    self.assertEqual(post('/api/update/check', {'X-Update-Token':manager.token,'Origin':base})[0], 202)
                    checked.assert_called_once_with(False)
                manager.local_busy = True
                self.assertEqual(post('/api/notes')[0], 409)
                manager.local_busy = False
                with urllib.request.urlopen(base + '/api/app') as response:
                    self.assertEqual(json.loads(response.read())['app'], 'literature-reviewer')
            finally:
                http.shutdown(); http.server_close(); thread.join(timeout=3)


class LauncherTests(unittest.TestCase):
    def exercise_restart(self, broken=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'installation'; fixture(root)
            private = personal(root)
            new = Path(tmp) / 'new'; fixture(new, '2.0.0', broken=broken)
            content = package(new)
            checksum = hashlib.sha256(content).hexdigest()
            release = {'version':'2.0.0', 'url':updates.RELEASE_URL, 'notes':'fixture', 'assets':[
                {'url':'package', 'size':len(content), 'digest':'sha256:' + checksum}, {'url':'checksum'}]}
            manager = updates.Updater(root, supervised=True)
            manager.release = release
            ready = threading.Event(); manager.on_ready = ready.set
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
            def get():
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/app', timeout=1) as response: return json.loads(response.read())
            def post(path):
                with urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}/' + path, data=b'{}'), timeout=3) as response: return response.read()
            def fetch(url, limit, progress=None, output=None):
                if output:
                    Path(output).write_bytes(content)
                    if progress: progress(len(content), len(content))
                    return b''
                return (checksum + '  ' + updates.PACKAGE + '\n').encode()
            with (Path(tmp) / 'launcher.log').open('w', encoding='utf-8') as log:
                process = subprocess.Popen([sys.executable, str(root / 'scripts/launch.py'), str(port)], stdout=log, stderr=log)
                try:
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        try:
                            if get().get('version') == '1.0.0': break
                        except OSError: pass
                        time.sleep(.05)
                    else: self.fail('old server did not start')
                    with patch.object(updates, 'latest_release', return_value=release), patch.object(updates, 'fetch', side_effect=fetch):
                        manager.start('2.0.0')
                        self.assertTrue(ready.wait(5), manager.status())
                    post('handoff')
                    deadline = time.monotonic() + 15
                    expected = 'rolled_back' if broken else 'completed'
                    while time.monotonic() < deadline:
                        result = updates.read_json(root / '.updates/status.json')
                        if result.get('phase') == expected:
                            try:
                                value = get()
                                if value['version'] == ('1.0.0' if broken else '2.0.0'): break
                            except OSError: pass
                        time.sleep(.1)
                    else: self.fail('update did not reach expected state: ' + str(result))
                    for name, original in private.items(): self.assertEqual((root / name).read_bytes(), original)
                    self.assertFalse((root / '.updates/last-backup' / updates.PACKAGE).exists())
                finally:
                    try: post('stop')
                    except OSError: pass
                    try: process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.terminate(); process.wait(timeout=5)

    def test_real_launcher_replaces_program_and_reconnects(self): self.exercise_restart()

    def test_real_launcher_rolls_back_when_new_server_cannot_start(self): self.exercise_restart(broken=True)


if __name__ == '__main__': unittest.main()
