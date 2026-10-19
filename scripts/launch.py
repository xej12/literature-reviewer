"""Keep the normal console open across verified program updates and rollbacks."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / '.updates'


def read(path):
    try: return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError): return {}


def status(value):
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    temporary = DIRECTORY / 'status-launcher.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, DIRECTORY / 'status.json')


def probe(port):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/app', timeout=1) as response:
            return json.loads(response.read(10000))
    except (OSError, ValueError): return {}


def work(plan):
    import re
    identifier = plan.get('id', '')
    if not re.fullmatch('[a-f0-9]{32}', identifier): raise RuntimeError('Invalid update transaction')
    path = DIRECTORY / ('work-' + identifier)
    if path.resolve() != ROOT.resolve() / '.updates' / ('work-' + identifier):
        raise RuntimeError('Unsafe update directory')
    return path


def worker(action, plan):
    path = work(plan)
    with (DIRECTORY / 'update.log').open('a', encoding='utf-8') as log:
        return subprocess.run([sys.executable, str(path / 'worker.py'), action, str(ROOT)],
                              stdout=log, stderr=log).returncode == 0


def discard_staging(plan):
    path = work(plan)
    # Keep one small backup of changed program files, not duplicate 45 MB ZIPs.
    for name in ('new',):
        if (path / name).exists(): shutil.rmtree(path / name)
    for name in ('literature-reviewer-windows-x64.zip',):
        (path / name).unlink(missing_ok=True)
    previous = DIRECTORY / 'last-backup'
    if previous.exists(): shutil.rmtree(previous)
    if path.exists(): path.rename(previous)
    (DIRECTORY / 'plan.json').unlink(missing_ok=True)


def stop_owned(process):
    if process.poll() is None:
        process.terminate()
        try: process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()  # Only the child launched here, never another user's service.
            process.wait(timeout=5)


def start_server(port, update_id=''):
    boot = secrets.token_hex(16)
    env = {**os.environ, 'LITERATURE_REVIEWER_LAUNCHER': '1', 'LITERATURE_REVIEWER_INSTANCE': boot,
           'LITERATURE_REVIEWER_BOOT_UPDATE': update_id, 'PYTHONIOENCODING': 'utf-8'}
    process = subprocess.Popen([sys.executable, str(ROOT / 'scripts/server.py'), str(port)], env=env)
    return process, boot


def wait_ready(process, port, boot, expected=None):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and process.poll() is None:
        info = probe(port)
        if info.get('instanceId') == boot and info.get('app') == 'literature-reviewer':
            return not expected or info.get('version') == expected
        time.sleep(.25)
    return False


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get('LITERATURE_REVIEWER_PORT', '8765'))
    existing = probe(port)
    if existing.get('app') == 'literature-reviewer':
        print(f'Already running. Open http://127.0.0.1:{port}/')
        return 0
    process = None
    try:
        plan = read(DIRECTORY / 'plan.json')
        pending = read(DIRECTORY / 'status.json')
        if not plan and pending.get('phase') in {'downloading', 'verifying'}:
            # Staging is disposable; it never touched installed program files.
            path = work(pending)
            if path.exists(): shutil.rmtree(path)
            status({**pending, 'phase': 'failed', 'message': '上次下载中断，当前程序未修改，请重新检查更新。'})
        if plan and pending.get('id') == plan.get('id') and pending.get('phase') in {'ready', 'installing', 'restarting'}:
            # Power loss during replacement: recover before importing app code.
            if (work(plan) / 'journal.json').exists():
                if not worker('--rollback', plan):
                    print('Recovery failed. Keep .updates/ and see .updates/update.log.')
                    return 1
            else: status({**plan, 'phase': 'failed', 'message': '上次更新在安装前中断，当前程序未修改，请重新检查更新。'})
            discard_staging(plan)
        process, boot = start_server(port)
        while True:
            result = process.wait()
            if result != 75: return result
            plan = read(DIRECTORY / 'plan.json')
            pending = read(DIRECTORY / 'status.json')
            if not plan or pending.get('id') != plan.get('id') or pending.get('phase') != 'ready':
                print('No verified update plan. Not replacing files.')
                return 1
            applied = worker('--apply', plan)
            if applied:
                process, boot = start_server(port, plan['id'])
                if wait_ready(process, port, boot, plan['version']):
                    status({**plan, 'phase': 'completed', 'message': f'已更新至 v{plan["version"]}，个人资料已保留。'})
                    try: discard_staging(plan)
                    except OSError: pass  # Cleanup failure must never undo a working update.
                    continue
                stop_owned(process)
            # apply_update restores immediately on a replacement error; retrying
            # that restoration is safe, and covers new-server startup failures.
            if (work(plan) / 'journal.json').exists():
                if not worker('--rollback', plan):
                    status({**plan, 'phase': 'recovery_failed', 'message': '自动恢复未完成，请保留 .updates 文件夹并查看 update.log；个人资料未被替换。'})
                    return 1
            else: status({**plan, 'phase': 'failed', 'message': '更新前检查未通过，已保留旧版。详情见 .updates/update.log。'})
            process, boot = start_server(port)
            if not wait_ready(process, port, boot):
                print('Old program could not start. See .updates/update.log.')
                stop_owned(process)
                return 1
            try: discard_staging(plan)
            except OSError: pass
    except KeyboardInterrupt:
        if process: stop_owned(process)
        return 0
    finally:
        if process and process.poll() is None: stop_owned(process)


if __name__ == '__main__':
    sys.exit(main())
