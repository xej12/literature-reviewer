"""Cancellation integration with a local fake provider; no paid requests."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import select
import tempfile
import threading
import unittest
import urllib.request
import uuid
from unittest.mock import Mock, patch

from PIL import Image

spec = importlib.util.spec_from_file_location('reviewer_cancel', Path(__file__).resolve().parents[1] / 'scripts/server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
jobs = server.request_jobs


class CancellationTests(unittest.TestCase):
    def test_uncancelled_transport_returns_complete_answer(self):
        class Provider(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                answer = b'{"answer":"complete"}'
                self.send_response(200)
                self.send_header('Content-Length',str(len(answer)))
                self.end_headers()
                self.wfile.write(answer)

        provider = ThreadingHTTPServer(('127.0.0.1',0),Provider)
        threading.Thread(target=provider.serve_forever,daemon=True).start()
        identifier = uuid.uuid4().hex
        try:
            with jobs.scope(identifier):
                request = urllib.request.Request(f'http://127.0.0.1:{provider.server_port}/model',data=b'{}')
                with jobs.urlopen(request,timeout=3) as reply:
                    self.assertEqual(json.loads(jobs.read(reply)),{'answer':'complete'})
            self.assertEqual(jobs.cancel(identifier)['state'],'completed')
        finally:
            provider.shutdown(); provider.server_close()

    def test_cancel_before_start_is_a_tombstone_not_a_new_model_request(self):
        identifier = uuid.uuid4().hex
        self.assertTrue(jobs.cancel(identifier)['cancelled'])
        with self.assertRaises(jobs.Cancelled), jobs.scope(identifier):
            self.fail('A cancelled request must never start')

    def test_active_cancel_interrupts_waiting_headers_and_waiting_body(self):
        for send_headers in (False, True):
            with self.subTest(send_headers=send_headers):
                self.cancel_active_request(send_headers)

    def cancel_active_request(self, send_headers):
        started, disconnected = threading.Event(), threading.Event()
        received = []

        class Provider(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                if send_headers:
                    self.send_response(200)
                    self.send_header('Content-Type','application/json')
                    self.send_header('Content-Length','100000')
                    self.end_headers()
                    self.wfile.write(b'{"choices":[')
                    self.wfile.flush()
                started.set()
                # This fake provider stops "generating" as soon as its peer
                # disconnects, rather than simply ignoring a browser abort.
                for _ in range(100):
                    if select.select([self.connection],[],[],0.03)[0]:
                        try:
                            closed = not self.connection.recv(1)
                        except OSError:
                            closed = True
                        if closed:
                            disconnected.set()
                            return

        provider = ThreadingHTTPServer(('127.0.0.1',0),Provider)
        app = server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        for http in (provider,app):
            threading.Thread(target=http.serve_forever,daemon=True).start()
        store = Mock()
        store.item.return_value = {'key':'TEST','title':'Paper','attachments':[{'key':'PDF'}]}
        store.pdf_page.return_value = {'page':2,'pageCount':4}
        image = io.BytesIO(); Image.new('RGB',(30,30),'white').save(image,format='PNG')
        store.pdf_page_image.return_value = image.getvalue()
        config = {'configured':True,'baseUrl':f'http://127.0.0.1:{provider.server_port}', 'model':'mock-only','apiKey':'fake'}
        identifier = uuid.uuid4().hex
        endpoint = f'http://127.0.0.1:{app.server_port}'
        try:
            with tempfile.TemporaryDirectory() as directory, patch.object(server,'STORE',store), \
                 patch.object(server,'ANALYSIS_DIR',Path(directory)), patch.object(server,'model_config',return_value=config):
                old = {'description':'Preserve existing interpretation','page':2,'attachmentKey':'PDF'}
                server.save_figure('TEST','PDF:2',{'figure':old})

                def generate():
                    request = urllib.request.Request(endpoint+'/api/items/TEST/figure',
                        data=json.dumps({'attachmentKey':'PDF','page':2,'force':True}).encode(),
                        headers={'Content-Type':'application/json','X-Generation-ID':identifier})
                    with urllib.request.urlopen(request,timeout=5) as reply:
                        return json.load(reply)

                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(generate)
                    self.assertTrue(started.wait(3), 'Fake provider did not receive the generation')
                    request = urllib.request.Request(endpoint+f'/api/generations/{identifier}/cancel',data=b'',method='POST')
                    with urllib.request.urlopen(request,timeout=3) as reply:
                        self.assertTrue(json.load(reply)['cancelled'])
                    self.assertEqual(future.result(timeout=3),{'cancelled':True})
                    self.assertTrue(disconnected.wait(2),'Upstream HTTP socket remained connected')
                saved = server.load_analysis('TEST')
                self.assertEqual(saved['figures']['PDF:2'],old)
                self.assertFalse(saved.get('figureDrafts'))
                self.assertEqual(len(received),1)
        finally:
            for http in (app,provider):
                http.shutdown(); http.server_close()

    def test_cancel_while_waiting_for_lock_prevents_later_generation(self):
        identifier = uuid.uuid4().hex
        waiting = threading.Event()
        with server.figure_reading.LOCK:
            def generate():
                with jobs.scope(identifier):
                    waiting.set()
                    return server.figure_lesson('TEST','PDF',1,None)
            with patch.object(server,'generate_figure',side_effect=AssertionError('No model calls')):
                pool = ThreadPoolExecutor(max_workers=1)
                future = pool.submit(generate)
                self.assertTrue(waiting.wait(2))
                jobs.cancel(identifier)
        try:
            with self.assertRaises(jobs.Cancelled):
                future.result(timeout=2)
        finally:
            pool.shutdown()

    def test_invalid_and_reused_ids_cannot_attach_to_another_job(self):
        for identifier in ('', 'bad-id', '../wrong', 'A'*32):
            with self.assertRaises(ValueError):
                jobs.cancel(identifier)
        identifier = uuid.uuid4().hex
        with jobs.scope(identifier):
            jobs.check()
        self.assertEqual(jobs.cancel(identifier)['state'],'completed')
        with self.assertRaises(ValueError), jobs.scope(identifier):
            pass


if __name__ == '__main__':
    unittest.main()
