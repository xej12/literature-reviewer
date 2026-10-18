"""Cancel local generation jobs and interrupt their upstream HTTP sockets."""
from contextlib import contextmanager
import http.client
import re
import socket
import threading
import time
import urllib.request


class Cancelled(RuntimeError):
    pass


class Job:
    def __init__(self):
        self.cancelled = threading.Event()
        self.sockets = []
        self.lock = threading.Lock()
        self.started = False
        self.finished = None

    def check(self):
        if self.cancelled.is_set():
            raise Cancelled('本次生成已取消，已有结果保留。')

    def bind(self, sock):
        with self.lock:
            self.sockets.append(sock)
        if self.cancelled.is_set():
            self.stop_socket(sock)
        self.check()

    @staticmethod
    def stop_socket(sock):
        # Closing a response file can wait for its read lock. Socket shutdown
        # instead wakes a thread blocked in getresponse/read immediately.
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass

    def cancel(self):
        self.cancelled.set()
        with self.lock:
            sockets = list(self.sockets)
        for sock in sockets:
            self.stop_socket(sock)


_jobs = {}
_lock = threading.Lock()
_local = threading.local()


def _valid(identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{32}', identifier):
        raise ValueError('无效的生成请求编号')


def _prune():
    now = time.monotonic()
    for key, job in list(_jobs.items()):
        if job.finished is not None and now - job.finished > 300:
            del _jobs[key]


def cancel(identifier):
    _valid(identifier)
    with _lock:
        _prune()
        job = _jobs.get(identifier)
        if job is None:
            # Cancellation can arrive before the generation POST. Retain a
            # short-lived tombstone so that request can never start billing.
            job = _jobs[identifier] = Job()
            job.finished = time.monotonic()
        elif job.finished is not None and job.started:
            return {'cancelled':False, 'state':'completed'}
    job.cancel()
    return {'cancelled':True, 'state':'cancelled'}


@contextmanager
def scope(identifier=None):
    if identifier is None:
        yield
        return
    _valid(identifier)
    with _lock:
        _prune()
        job = _jobs.setdefault(identifier, Job())
        if job.started:
            raise ValueError('生成请求编号已使用，请勿重复提交')
        job.started = True
        job.finished = None
    previous = getattr(_local, 'job', None)
    _local.job = job
    try:
        job.check()
        yield
    finally:
        with _lock:
            job.finished = time.monotonic()
        with job.lock:
            job.sockets.clear()
        _local.job = previous


def check():
    job = getattr(_local, 'job', None)
    if job:
        job.check()


def read(response):
    try:
        return response.read()
    finally:
        # A socket shutdown may produce EOF or IncompleteRead, depending on
        # whether the provider had sent its headers. Both mean cancellation.
        check()


def urlopen(request, timeout, fallback=None):
    job = getattr(_local, 'job', None)
    if job is None:
        return (fallback or urllib.request.urlopen)(request, timeout=timeout)
    job.check()

    def connection(base):
        class Connection(base):
            def connect(self):
                job.check()
                # No model body is sent until connect returns. Bound setup
                # time while still allowing long generation reads.
                read_timeout = self.timeout
                self.timeout = min(read_timeout, 15)
                try:
                    super().connect()
                    job.bind(self.sock)
                    self.sock.settimeout(read_timeout)
                finally:
                    self.timeout = read_timeout
        return Connection

    class HTTP(urllib.request.HTTPHandler):
        def http_open(self, req):
            return self.do_open(connection(http.client.HTTPConnection), req)

    class HTTPS(urllib.request.HTTPSHandler):
        def https_open(self, req):
            return self.do_open(connection(http.client.HTTPSConnection), req, context=self._context)

    # Preserve urllib's environment proxy, redirects and certificate checks.
    opener = urllib.request.build_opener(HTTP(), HTTPS())
    try:
        response = opener.open(request, timeout=timeout)
        job.check()
        return response
    except Exception:
        job.check()
        raise
