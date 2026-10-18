# Literature Reviewer

[中文](README.md) · [Windows setup (Chinese)](docs/installation.md) · [Troubleshooting (Chinese)](docs/troubleshooting.md)

A local web app for reading papers from your own Zotero desktop library. Generate explanations of methods, formulas, terminology and figures on demand, compare them with the original PDF, and revisit saved results without regenerating them.

**Current platform: Windows, Python 3.11+.** There is no standalone installer. macOS/Linux are not supported yet because the server imports Windows registry APIs. Codex, Node.js and Zotero plugins are not required for normal use. The interface and most documentation are currently in Chinese.

## Quick start

1. Install [Zotero](https://www.zotero.org/download/) and download at least one PDF attachment locally.
2. Install [Python 3.11+](https://www.python.org/downloads/windows/) with “Add python.exe to PATH” selected.
3. Download and extract this repository using **Code → Download ZIP**, or clone it with Git.
4. Open PowerShell in the extracted project folder and run:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
   ```

5. Visit <http://127.0.0.1:8765>. Keep the terminal open. For later sessions, double-click `start.cmd`; stop with Ctrl+C.
6. Open **模型设置** (Model settings). Enter your provider's Chat Completions base URL, exact model ID and API key. Do not append `/chat/completions` to the base URL. Saving is local; testing the connection makes a real request and may incur charges.

If Zotero is not detected, set the directory containing `zotero.sqlite` before starting:

```powershell
$env:ZOTERO_DATA_DIR = "D:\Your Zotero Directory"
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

Check the environment without network or model calls:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1 -Check
```

For figure previews/analysis and source-page images, install [Poppler for Windows](https://github.com/oschwartz10612/poppler-windows/releases) and add the folder containing `pdfinfo.exe` and `pdftoppm.exe` (usually `Library\bin`) to your user PATH. Reopen the terminal and restart the server. Figure analysis also requires an image-capable model. Installing `pdf2image` alone does not install Poppler.

## Features and limits

- Read-only Zotero browsing, collection filters and direct original PDF access.
- On-demand paper chapters and terminology lessons with source snippets, formula rendering and PDF page navigation.
- Selectable PDF text, a personal glossary and contextual translation.
- Side-by-side figure explanations with optional region selection.
- Local caches/history and reading priorities based primarily on your research goals and paper content.
- Optional CAS/JCR journal data import: `.\.venv\Scripts\python.exe scripts/import_journals.py`. This downloads a pinned third-party dataset; it is not live official data, and SJR is not used as a replacement for JCR.

Viewing cached results is free of model calls; generating, regenerating, uncached translation and connection tests may use your paid API. Closing an analysis window cancels local work and disconnects the upstream request; provider-side cancellation and billing remain provider-dependent. Scanned PDFs have no OCR support. Source locations help verification but do not guarantee correct explanations.

## Your data

The server binds to `127.0.0.1` and has no login or multi-user isolation. Other users should run their own copy with their own Zotero library. Do not expose this service to the internet.

Settings and results live in local `data/`, which is excluded from Git. **API keys are stored there in plaintext.** Model-backed actions send relevant paper text or selected images to your configured provider. Back up `data/` privately before upgrading; your Zotero library requires its own backup. Never upload these directories with an issue.

## Contributing and licensing

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) and the issue templates. Tests do not require a paid model API. The original project code and documentation are [MIT licensed](LICENSE); bundled dependencies and third-party datasets retain their own terms. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
