"""Discover project-local Poppler without downloads or system PATH changes."""
from __future__ import annotations

import os
from pathlib import Path


def configure(project_root: Path | None = None) -> Path | None:
    root = (project_root or Path(__file__).resolve().parents[1]) / 'vendor' / 'poppler' / 'runtime'
    if not root.is_dir():
        return None
    for tool in sorted(root.rglob('pdfinfo.exe')):
        directory = tool.parent
        if (directory / 'pdftoppm.exe').is_file():
            current = os.environ.get('PATH', '')
            if str(directory) not in current.split(os.pathsep):
                os.environ['PATH'] = str(directory) + os.pathsep + current
            return directory
    return None
