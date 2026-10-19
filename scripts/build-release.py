"""Build a Windows ZIP from committed files, with a verified Poppler archive.

Run after committing: python scripts/build-release.py --poppler path/to/Release.zip
No working-tree data, local settings or virtual environments are copied.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'literature-reviewer/'


def build(poppler: Path, output: Path) -> Path:
    # Read both manifest and project files from the same commit.
    source = subprocess.check_output(['git', 'archive', '--format=zip', 'HEAD'], cwd=ROOT)
    with zipfile.ZipFile(io.BytesIO(source)) as tracked:
        manifest = json.loads(tracked.read('vendor/poppler/manifest.json'))
        with poppler.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != manifest['sha256']:
            raise ValueError('Poppler SHA256 does not match the committed manifest')
        with zipfile.ZipFile(poppler) as binary:
            names = {PurePosixPath(n).name for n in binary.namelist()}
            if not {'pdfinfo.exe', 'pdftoppm.exe'} <= names:
                raise ValueError('Poppler archive is missing required tools')
        output.parent.mkdir(parents=True, exist_ok=True)
        release_files = {}
        version = json.loads(tracked.read('version.json'))['version']
        with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as release:
            for name in tracked.namelist():
                if name.endswith('/'):
                    continue
                # Refuse accidental private-data commits instead of releasing them.
                parts = PurePosixPath(name).parts
                if parts[0] in {'data', '.venv', 'venv', '.git', '.build', 'dist', '.updates'} or parts[0].startswith('.env') or name == 'release-files.json':
                    raise ValueError(f'Private/build file tracked in Git: {name}')
                content = tracked.read(name)
                release.writestr(PREFIX + name, content)
                release_files[name] = hashlib.sha256(content).hexdigest()
            # Preserve upstream's original archive and embedded notices byte-for-byte.
            release.write(poppler, PREFIX + 'vendor/poppler/windows-x64.zip', compress_type=zipfile.ZIP_STORED)
            release_files['vendor/poppler/windows-x64.zip'] = digest
            release.writestr(PREFIX + 'release-files.json', json.dumps(
                {'format': 1, 'version': version, 'files': release_files}, ensure_ascii=False, indent=2))
    with output.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    checksum = output.with_suffix('.zip.sha256')
    checksum.write_text(f'{digest}  {output.name}\n', encoding='ascii')
    return checksum


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--poppler', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/literature-reviewer-windows-x64.zip')
    args = parser.parse_args()
    print(build(args.poppler.resolve(), args.output.resolve()))
