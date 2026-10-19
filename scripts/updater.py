"""Portable-release updates. Personal data and the Python environment are never managed.

The web server only stages a verified release. launch.py waits for the old server
to exit before invoking a private copy of this module to replace program files.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import stat
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPOSITORY = 'xej12/literature-reviewer'
RELEASE_URL = f'https://github.com/{REPOSITORY}/releases/latest'
API = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
PACKAGE = 'literature-reviewer-windows-x64.zip'
MANIFEST = 'release-files.json'
MAX_DOWNLOAD = 200 * 1024 * 1024
BUSY_PHASES = {'downloading', 'verifying', 'ready', 'installing', 'restarting'}
ROOT_FILES = {'version.json', MANIFEST, 'requirements.txt', 'setup.cmd', 'start.cmd',
              'README.md', 'README.en.md', 'LICENSE', 'CONTRIBUTING.md', 'SECURITY.md',
              'SKILL.md', 'THIRD_PARTY_NOTICES.md', '.gitignore'}
ROOT_DIRS = {'scripts', 'web', 'docs', 'references', 'agents', 'tests', '.github', 'vendor'}


def version(value):
    match = re.fullmatch(r'v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', str(value))
    if not match:
        raise ValueError('发行版本号必须为 v主版本.次版本.修订号')
    return tuple(map(int, match.groups()))


def current_version(root):
    try:
        value = json.loads((Path(root) / 'version.json').read_text(encoding='utf-8'))['version']
        version(value)
        return value
    except (OSError, ValueError, KeyError, TypeError):
        return '0.0.0'


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {} if default is None else default


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + secrets.token_hex(4) + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def managed_path(name):
    """Reject traversal, Windows aliases, protected trees and case collisions."""
    if not isinstance(name, str) or '\\' in name or ':' in name or '\x00' in name:
        raise ValueError('更新包包含无效路径')
    parts = name.split('/')
    if any(not p or p in {'.', '..'} or p.endswith((' ', '.')) or re.search(r'[<>"|?*\x00-\x1f]', p)
           or p.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(10)), *(f'LPT{i}' for i in range(10))}
           for p in parts):
        raise ValueError('更新包包含不安全路径')
    if not ((len(parts) == 1 and name in ROOT_FILES) or (len(parts) > 1 and parts[0] in ROOT_DIRS)):
        raise ValueError('更新包试图修改个人资料或非程序文件：' + name)
    if any(p.casefold() in {'.git', '.venv', '__pycache__', 'data', '.updates', 'node_modules'} for p in parts):
        raise ValueError('更新包包含受保护目录')
    if name.casefold().startswith('vendor/poppler/runtime/') or name.casefold().startswith('vendor/poppler/.install-'):
        raise ValueError('更新包不应覆盖已安装的 Poppler 运行时')
    return name


def safe_target(root, name):
    managed_path(name)
    path = Path(root).joinpath(*name.split('/'))
    # Windows junctions may not report is_symlink(), but resolve() follows them.
    if not path.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('程序目录中的链接指向了安装目录之外')
    for parent in (path, *path.parents):
        if parent == Path(root): break
        if parent.is_symlink() or (hasattr(parent, 'is_junction') and parent.is_junction()):
            raise ValueError('程序目录包含符号链接或目录联接，请手动升级')
    return path


def files_manifest(value):
    if not isinstance(value, dict) or value.get('format') != 1 or not isinstance(value.get('files'), dict):
        raise ValueError('安装包缺少受支持的程序文件清单，请手动升级')
    version(value.get('version'))
    result, seen = {}, set()
    for name, digest in value['files'].items():
        managed_path(name)
        if name == MANIFEST or name.casefold() in seen or not re.fullmatch(r'[a-f0-9]{64}', str(digest)):
            raise ValueError('程序文件清单无效或存在重复路径')
        seen.add(name.casefold())
        result[name] = digest
    if not {'version.json', 'scripts/server.py', 'scripts/launch.py', 'scripts/updater.py',
            'web/index.html', 'requirements.txt', 'vendor/poppler/manifest.json'} <= result.keys():
        raise ValueError('更新包缺少必要程序文件')
    return result


def extract_verified(archive, destination, expected_version):
    with zipfile.ZipFile(archive) as bundle:
        names = {}
        total = 0
        for info in bundle.infolist():
            if info.is_dir(): continue
            if not info.filename.startswith('literature-reviewer/') or info.flag_bits & 1:
                raise ValueError('更新包目录格式不正确')
            name = managed_path(info.filename[len('literature-reviewer/'):])
            if name.casefold() in names or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError('更新包包含重复文件或符号链接')
            names[name.casefold()] = (name, info)
            total += info.file_size
        if total > 600 * 1024 * 1024 or len(names) > 15000:
            raise ValueError('更新包解压后过大')
        manifest = json.loads(bundle.read('literature-reviewer/' + MANIFEST))
        files = files_manifest(manifest)
        if version(manifest['version']) != version(expected_version):
            raise ValueError('更新包版本与 Release 不一致')
        if set(name for name, _ in names.values()) != {*files, MANIFEST}:
            raise ValueError('更新包与程序文件清单不一致')
        for name, info in names.values():
            content = bundle.read(info)
            if name != MANIFEST and hashlib.sha256(content).hexdigest() != files[name]:
                raise ValueError('程序文件校验失败：' + name)
            path = safe_target(destination, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        if current_version(destination) != manifest['version']:
            raise ValueError('程序版本文件与清单不一致')
    return files


class GitHubLimited(RuntimeError):
    pass


def fetch(url, limit, progress=None, output=None, final_url=False):
    accept = 'application/vnd.github+json' if url == API else 'text/html' if final_url else 'application/octet-stream'
    request = urllib.request.Request(url, headers={'User-Agent': 'LiteratureReviewer-Updater', 'Accept': accept})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                size = int(response.headers.get('Content-Length', '0'))
                if size > limit: raise ValueError('下载文件超过大小限制')
                chunks, received = [], 0
                deadline = time.monotonic() + 600
                stream = Path(output).open('wb') if output else None
                try:
                    while chunk := response.read(256 * 1024):
                        received += len(chunk)
                        if received > limit: raise ValueError('下载文件超过大小限制')
                        if time.monotonic() > deadline: raise TimeoutError('download timed out')
                        if stream: stream.write(chunk)
                        else: chunks.append(chunk)
                        if progress: progress(received, size)
                finally:
                    if stream: stream.close()
                result = b''.join(chunks)
                return (result, response.geturl()) if final_url else result
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429): raise GitHubLimited('GitHub 暂时限制了访问，请稍后重试或打开发布页面。') from None
            raise RuntimeError(f'GitHub 下载失败（HTTP {exc.code}），现有版本保留。') from None
        except (OSError, urllib.error.URLError, http.client.HTTPException) as exc:
            if attempt == 1: raise RuntimeError('无法连接 GitHub，请检查网络后重试；现有版本保留。') from exc
            time.sleep(1)


def latest_release():
    try:
        release = json.loads(fetch(API, 2 * 1024 * 1024))
    except GitHubLimited:
        # Public API quotas are shared on some networks. GitHub's own /latest
        # redirect still identifies the stable release, without a user's token.
        _, url = fetch(RELEASE_URL, 2 * 1024 * 1024, final_url=True)
        prefix = f'https://github.com/{REPOSITORY}/releases/tag/'
        if not url.startswith(prefix): raise ValueError('无法从 GitHub 发布页面确认正式版本')
        tag = url[len(prefix):]
        version(tag)
        return {'version': tag.lstrip('v'), 'url': url,
                'notes': 'GitHub 版本接口暂时受限，已通过官方发布页面确认版本。完整更新说明请点击下方“GitHub 发布页面”。',
                'assets': [{'url': f'https://github.com/{REPOSITORY}/releases/download/{tag}/{name}', 'size': None, 'digest': None}
                           for name in (PACKAGE, PACKAGE + '.sha256')]}
    tag = release.get('tag_name', '')
    version(tag)
    if release.get('draft') or release.get('prerelease'):
        raise ValueError('只接受正式稳定版本')
    assets = {a['name']: a for a in release.get('assets', [])}
    selected = []
    for name in (PACKAGE, PACKAGE + '.sha256'):
        asset = assets.get(name, {})
        expected = f'https://github.com/{REPOSITORY}/releases/download/{tag}/{name}'
        if asset.get('browser_download_url') != expected or asset.get('state') != 'uploaded':
            raise ValueError('最新 Release 尚未提供完整的 Windows 安装包和校验文件')
        if not 0 < asset.get('size', 0) <= (MAX_DOWNLOAD if name == PACKAGE else 1024):
            raise ValueError('发行附件大小无效')
        selected.append({'url': expected, 'size': asset['size'], 'digest': asset.get('digest')})
    return {'version': tag.lstrip('v'), 'url': f'https://github.com/{REPOSITORY}/releases/tag/{tag}',
            'notes': str(release.get('body') or '作者没有填写更新说明。')[:12000], 'assets': selected}


class Busy(RuntimeError):
    pass


class Updater:
    def __init__(self, root, supervised=False):
        self.root = Path(root).resolve()
        self.directory = self.root / '.updates'
        self.supervised = supervised
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.writes = 0
        self.checking = False
        self.release = None
        self.check_error = ''
        self.checked = 0
        self.on_ready = None
        self.cache = read_json(self.directory / 'check.json')
        try:
            if not isinstance(self.cache, dict): raise ValueError('Invalid cache')
            if not isinstance(self.cache.get('checkedAt', 0), (int, float)): raise ValueError('Invalid time')
            cached_release = self.cache.get('release')
            if cached_release:
                version(cached_release['version'])
                if not isinstance(cached_release.get('notes'), str): raise ValueError('Invalid notes')
        except (ValueError, KeyError, TypeError): self.cache = {}
        # A completed prior download is not authority to resume a replacement.
        self.local_busy = False

    def support(self):
        if self.directory.is_symlink() or self.directory.resolve() != self.root / '.updates': return '更新目录包含链接，请移除链接后重试。'
        if (self.root / '.git').exists(): return '当前是 Git 开发目录，为保护代码修改，仅检查版本。发行安装包支持一键更新。'
        if not (self.root / MANIFEST).is_file(): return '当前目录缺少更新清单，请先手动安装一次支持更新的新版安装包。'
        if not self.supervised: return '请通过 start.cmd 重新启动网站后使用一键更新。'
        return ''

    def status(self):
        with self.lock:
            saved = read_json(self.directory / 'status.json')
            if not isinstance(saved, dict): saved = {}
            # An interrupted earlier process must never block all future writes.
            busy = self.local_busy or (self.supervised and os.environ.get('LITERATURE_REVIEWER_BOOT_UPDATE') == saved.get('id') and saved.get('phase') == 'restarting')
            release = self.release
            reason = self.support()
            return {'currentVersion': current_version(self.root), 'latestVersion': release['version'] if release else None,
                    'available': bool(release and version(release['version']) > version(current_version(self.root))),
                    'supported': not reason, 'reason': reason, 'checking': self.checking,
                    'checkError': self.check_error, 'checkedAt': self.checked or None,
                    'releaseUrl': release['url'] if release else RELEASE_URL, 'notes': release['notes'] if release else '',
                    'token': self.token, 'busy': busy, 'operation': saved}

    @contextmanager
    def mutation(self):
        with self.lock:
            if self.status()['busy']: raise Busy('正在更新程序，请等待完成后再操作。')
            self.writes += 1
        try: yield
        finally:
            with self.lock: self.writes -= 1

    def check(self, force=False):
        with self.lock:
            if self.checking or self.status()['busy']: return self.status()
            cached = self.cache
            if not force and time.time() - cached.get('checkedAt', 0) < 24 * 3600:
                # Cache only public release data fetched from the fixed repository.
                self.release = cached.get('release')
                self.checked = cached.get('checkedAt', 0)
                self.check_error = cached.get('error', '')
                return self.status()
            self.checking = True

        def run():
            try:
                release = latest_release()
                with self.lock: self.release, self.check_error = release, ''
            except Exception as exc:
                with self.lock: self.check_error = str(exc)
            finally:
                with self.lock:
                    self.checked = time.time()
                    self.cache = {'release': self.release, 'checkedAt': self.checked, 'error': self.check_error}
                    try: write_json(self.directory / 'check.json', self.cache)
                    except OSError: pass  # A read-only directory should still be browsable.
                    self.checking = False
        threading.Thread(target=run, daemon=True).start()
        return self.status()

    def start(self, expected_version):
        with self.lock:
            if self.support(): raise ValueError(self.support())
            if self.status()['busy']: raise Busy('更新已经在进行，请勿重复点击。')
            if self.writes: raise Busy('还有生成、保存或检索任务正在进行，请等任务结束后再更新。')
            if not self.release or self.release['version'] != expected_version or version(expected_version) <= version(current_version(self.root)):
                raise ValueError('版本信息已变化，请重新检查更新。')
            if not callable(self.on_ready): raise RuntimeError('更新启动器尚未就绪。')
            identifier = secrets.token_hex(16)
            write_json(self.directory / 'status.json', {'id': identifier, 'phase': 'downloading', 'version': expected_version,
                                                       'message': '正在连接 GitHub 下载新版…', 'received': 0, 'total': self.release['assets'][0]['size']})
            self.local_busy = True
        threading.Thread(target=self._stage, args=(identifier, expected_version), daemon=True).start()
        return self.status()

    def _stage(self, identifier, expected_version):
        work = self.directory / ('work-' + identifier)
        def status(phase, message, **details):
            write_json(self.directory / 'status.json', {'id': identifier, 'phase': phase, 'version': expected_version, 'message': message, **details})
        try:
            # Never let junctions redirect update scratch files into personal data.
            if self.directory.is_symlink() or self.directory.resolve() != self.root / '.updates':
                raise ValueError('更新目录包含链接，请先移除链接后重试。')
            work.mkdir(parents=True)
            release = latest_release()  # Revalidate official URLs immediately before download.
            if release['version'] != expected_version: raise ValueError('最新版本已经变化，请重新检查更新。')
            package, checksum = release['assets']
            raw = fetch(checksum['url'], 1024).decode('ascii').strip()
            match = re.fullmatch(r'([a-fA-F0-9]{64})\s+\*?' + re.escape(PACKAGE), raw)
            if not match: raise ValueError('安装包 SHA256 校验文件格式无效')
            expected = match[1].lower()
            if package.get('digest') and package['digest'] != 'sha256:' + expected:
                raise ValueError('GitHub 附件校验值与校验文件不一致')
            last_write = [0]
            def progress(received, total):
                if time.monotonic() - last_write[0] > .4 or received == total:
                    status('downloading', '正在下载新版安装包…', received=received, total=total or package['size'])
                    last_write[0] = time.monotonic()
            archive = work / PACKAGE
            fetch(package['url'], MAX_DOWNLOAD, progress, archive)
            if (package['size'] is not None and archive.stat().st_size != package['size']) or sha256(archive) != expected:
                raise ValueError('安装包校验失败，请重新下载；现有程序未修改。')
            status('verifying', '正在校验并准备程序文件…')
            extract_verified(archive, work / 'new', expected_version)
            validate_installation(self.root, work / 'new')
            # Freeze the exact updater that staged this transaction. It must not
            # import application modules which will be replaced underneath it.
            shutil.copy2(Path(__file__), work / 'worker.py')
            write_json(self.directory / 'plan.json', {'id': identifier, 'version': expected_version})
            status('ready', '下载和校验完成，正在重新启动…')
            self.on_ready()
        except Exception as exc:
            status('failed', str(exc))
            with self.lock: self.local_busy = False
            if work.exists(): shutil.rmtree(work, ignore_errors=True)


def validate_installation(root, new):
    root, new = Path(root), Path(new)
    if (root / '.git').exists(): raise ValueError('不允许覆盖 Git 开发目录')
    old_files = files_manifest(read_json(root / MANIFEST))
    new_files = files_manifest(read_json(new / MANIFEST))
    for name, digest in new_files.items():
        path = safe_target(new, name)
        if not path.is_file() or sha256(path) != digest:
            raise ValueError('已下载的更新文件校验失败，请重新检查更新：' + name)
    for name, digest in old_files.items():
        path = safe_target(root, name)
        if not path.is_file() or sha256(path) != digest:
            raise ValueError('程序文件被修改或缺失，请备份后手动升级：' + name)
    for name in ('requirements.txt', 'vendor/poppler/manifest.json'):
        if (root / name).read_bytes().replace(b'\r\n', b'\n') != (new / name).read_bytes().replace(b'\r\n', b'\n'):
            raise ValueError('新版依赖或 Poppler 版本有变化，请按发布说明手动升级；当前版本未修改。')
    for name in new_files:
        path = safe_target(root, name)
        if name not in old_files and path.exists():
            raise ValueError('新版程序与已有自定义文件冲突，请手动升级：' + name)


def work_directory(root, identifier):
    if not re.fullmatch(r'[a-f0-9]{32}', str(identifier)): raise ValueError('无效更新事务')
    directory = Path(root) / '.updates' / ('work-' + identifier)
    if directory.resolve() != Path(root).resolve() / '.updates' / ('work-' + identifier):
        raise ValueError('更新目录包含不安全的链接')
    return directory


def apply_update(root, plan):
    root = Path(root).resolve()
    work = work_directory(root, plan['id'])
    new, backup = work / 'new', work / 'backup'
    validate_installation(root, new)
    old_files = files_manifest(read_json(root / MANIFEST))
    new_files = files_manifest(read_json(new / MANIFEST))
    # Only changed program files need a backup. data/, .venv/ and runtime/ are
    # not in either manifest and are never copied, removed or rewritten.
    changed = [name for name in {*old_files, *new_files, MANIFEST}
               if name == MANIFEST or old_files.get(name) != new_files.get(name)]
    journal = {'oldVersion': current_version(root), 'newVersion': current_version(new), 'files': {}}
    for name in sorted(changed):
        source = safe_target(root, name)
        journal['files'][name] = source.exists()
        if source.exists():
            target = safe_target(backup, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    write_json(work / 'journal.json', journal)  # Complete backup before first replacement.
    write_json(root / '.updates/status.json', {**plan, 'phase': 'installing', 'message': '正在替换程序文件，个人资料保持不变…'})
    try:
        for name in sorted(changed):
            target = safe_target(root, name)
            if name in new_files or name == MANIFEST:
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + '.update-tmp')
                shutil.copy2(safe_target(new, name), temporary)
                os.replace(temporary, target)
            elif target.exists(): target.unlink()
    except Exception:
        rollback(root, plan)
        raise
    write_json(root / '.updates/status.json', {**plan, 'phase': 'restarting', 'message': '程序已更新，正在检查新版启动…'})


def rollback(root, plan):
    root = Path(root).resolve()
    work = work_directory(root, plan['id'])
    journal = read_json(work / 'journal.json')
    if not isinstance(journal.get('files'), dict): raise RuntimeError('更新备份不存在，未尝试覆盖程序。')
    for name, existed in journal['files'].items():
        target = safe_target(root, name)
        if existed:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(safe_target(work / 'backup', name), target)
        elif target.exists(): target.unlink()
        temporary = target.with_name(target.name + '.update-tmp')
        if temporary.exists(): temporary.unlink()
    write_json(root / '.updates/status.json', {**plan, 'phase': 'rolled_back', 'message': '新版未能正常启动，已恢复旧程序。个人资料保持不变。'})


if __name__ == '__main__':
    root = Path(sys.argv[2]).resolve()
    plan = read_json(root / '.updates/plan.json')
    try:
        if sys.argv[1] == '--apply': apply_update(root, plan)
        elif sys.argv[1] == '--rollback': rollback(root, plan)
        else: raise ValueError('无效更新操作')
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
