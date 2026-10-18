"""Read isolated copies without taking SQLite locks on Zotero's live library."""
from contextlib import contextmanager
import hashlib
from pathlib import Path
import sqlite3
import tempfile


BUSY_MESSAGE = "Zotero 数据库正在变化或维护，暂未取得可验证的副本，请稍后刷新文献库。"


def _signature(paths):
    result = []
    for path in paths:
        try:
            stat = path.stat()
            result.append((stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
        except FileNotFoundError:
            result.append(None)
    return result


def _digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").digest()


def _copy_stable(source, target):
    # Never copy SHM: SQLite creates private coordination files for our copy.
    paths = [source, Path(str(source) + "-wal"), Path(str(source) + "-journal")]
    before = _signature(paths)
    if before[0] is None or (before[2] and before[2][1]):
        raise RuntimeError(BUSY_MESSAGE)
    digests = []
    for index, original in enumerate(paths[:2]):
        if before[index] is None:
            continue
        destination = target if index == 0 else Path(str(target) + "-wal")
        digest = hashlib.sha256()
        with original.open("rb") as reader, destination.open("wb") as writer:
            while block := reader.read(1024 * 1024):
                digest.update(block)
                writer.write(block)
        digests.append((original, digest.digest()))
    # Detect checkpoints, replacement, WAL appends and in-place updates during
    # copying. Retry rather than serve a partial or unverifiable library.
    if any(_digest(original) != digest for original, digest in digests) or _signature(paths) != before:
        raise RuntimeError(BUSY_MESSAGE)


@contextmanager
def connect_snapshot(source):
    """Include committed WAL content, validate, query only, then remove the copy.

    A filesystem copy is not SQLite's transactional backup API. Reject detected
    concurrent changes and invalid copies; never bypass locks on the live DB.
    """
    with tempfile.TemporaryDirectory(prefix="literature-zotero-") as directory:
        conn = None
        for attempt in range(3):
            # Each retry has its own directory, avoiding leftover recovered WAL.
            folder = Path(directory) / str(attempt)
            folder.mkdir()
            target = folder / "library.sqlite"
            try:
                _copy_stable(Path(source), target)
                # Writable *temporary* copy permits normal SQLite WAL recovery.
                conn = sqlite3.connect(target, timeout=0.5)
                conn.row_factory = sqlite3.Row
                if [row[0] for row in conn.execute("PRAGMA quick_check")] != ["ok"]:
                    raise RuntimeError(BUSY_MESSAGE)
                conn.execute("PRAGMA query_only=ON")
                break
            except (OSError, sqlite3.DatabaseError, RuntimeError):
                if conn is not None:
                    conn.close()
                    conn = None
                if attempt == 2:
                    raise RuntimeError(BUSY_MESSAGE) from None
        try:
            yield conn
        finally:
            conn.close()
