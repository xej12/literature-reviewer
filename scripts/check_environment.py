"""Read-only local checks. Does not import the server or call a model/network."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import sys
import poppler_runtime


def main() -> int:
    poppler_runtime.configure()
    failures = 0
    print("Literature Reviewer - local environment check (no network/model calls)")
    if sys.platform != "win32":
        print("[FAIL] This release supports Windows. macOS/Linux are not yet supported.")
        failures += 1
    else:
        print("[OK] Windows")
    if sys.version_info < (3, 11):
        print("[FAIL] Python 3.11+ is required.")
        failures += 1
    else:
        print(f"[OK] Python {sys.version.split()[0]}")
    for package in ("pypdf", "pdf2image", "PIL"):
        if importlib.util.find_spec(package) is None:
            print(f"[FAIL] Missing {package}. Install requirements.txt with this Python.")
            failures += 1
        else:
            print(f"[OK] Python package: {package}")
    for executable in ("pdfinfo", "pdftoppm"):
        if shutil.which(executable):
            print(f"[OK] Poppler command: {executable}")
        else:
            print(f"[WARN] {executable} is not on PATH; figure previews/analysis need Poppler.")
    if os.environ.get("LITERATURE_REVIEWER_DEMO") == "1":
        print("[OK] Demo mode: Zotero is not required; no model requests will be made")
        print("Checks complete. See docs/installation.md and docs/usage.md.")
        return 1 if failures else 0
    configured = os.environ.get("ZOTERO_DATA_DIR")
    candidates = [Path(configured).expanduser()] if configured else []
    candidates.extend([Path.home() / "Zotero", Path(os.environ.get("APPDATA", "")) / "Zotero/Zotero/Profiles"])
    found = any((p / "zotero.sqlite").is_file() or (p.is_dir() and any(p.glob("*/zotero.sqlite"))) for p in candidates)
    if configured and not (Path(configured).expanduser() / "zotero.sqlite").is_file():
        print("[WARN] ZOTERO_DATA_DIR does not directly contain zotero.sqlite. Check the data-directory setting.")
    print("[OK] Local Zotero database found" if found else "[WARN] Zotero database not found; set ZOTERO_DATA_DIR to its containing folder.")
    print("Checks complete. See docs/installation.md and docs/troubleshooting.md.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
