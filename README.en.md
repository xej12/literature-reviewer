# Literature Reviewer

[中文](README.md) · [Windows setup (Chinese)](docs/installation.md) · [Troubleshooting (Chinese)](docs/troubleshooting.md)

A local web app for reading papers from your own Zotero desktop library. Generate explanations of methods, formulas, terminology and figures on demand, compare them with the original PDF, and revisit saved results without regenerating them.

Literature discovery queries OpenAlex and Semantic Scholar for similar, referenced and citing papers, with source links, library badges and saved results. Open a paper and choose **查找相关文献**, or use **联合查找** in the sidebar to combine 2–5 papers with a research question. Joint discovery includes year/review/open-access filters, reversible dismissal and saved search groups. It does not call an LLM; external services may require separate API keys and impose quotas. See the [usage guide](docs/usage.md#发现相关文献).

Select candidates in either discovery view to download RIS, BibTeX, or a Markdown reading list with source evidence and note prompts. Exports use cached metadata, keep selections across filters with an explicit hidden count, and exclude dismissed papers. RIS/BibTeX use generic record types; verify missing metadata after importing. Downloads do not automatically modify Zotero.

**Current platform: Windows x64, Python 3.11+.** The [beginner ZIP includes Poppler](https://github.com/xej12/literature-reviewer/releases/latest/download/literature-reviewer-windows-x64.zip). Python and Zotero must be installed first; setup needs internet for Python packages. macOS/Linux/Windows ARM64 are not supported. Codex, Node.js and Zotero plugins are not required. The interface and most documentation are currently in Chinese.

## Quick start

1. Install [Zotero](https://www.zotero.org/download/) and download at least one PDF attachment locally.
2. Install [Python 3.11+](https://www.python.org/downloads/windows/) with “Add python.exe to PATH” selected.
3. Download and extract the [Windows x64 beginner ZIP](https://github.com/xej12/literature-reviewer/releases/latest/download/literature-reviewer-windows-x64.zip). Select this asset, rather than GitHub's automatic “Source code” ZIP.
4. Double-click `setup.cmd`. It creates `.venv`, installs Python dependencies, verifies/extracts bundled Poppler, and starts the app. No manual PATH edits or administrator privileges are needed. A source ZIP or Git checkout also supports `setup.cmd`, but downloads the same pinned Poppler build on first setup.

5. Visit <http://127.0.0.1:8765>. Keep the terminal open. For later sessions, double-click `start.cmd`; stop with Ctrl+C.
6. Open **模型设置** (Model settings). Enter your provider's Chat Completions base URL, exact model ID and API key. Do not append `/chat/completions` to the base URL. Saving is local; testing the connection checks `/models` without generating content.

If Zotero is not detected, set the directory containing `zotero.sqlite` before starting:

```powershell
$env:ZOTERO_DATA_DIR = "D:\Your Zotero Directory"
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

Check the environment without network or model calls:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1 -Check
```

Poppler is installed inside `vendor/poppler/runtime/`; only the server process PATH is adjusted. Normal `start.cmd` does not download anything. Run `setup.cmd` again to finish an incomplete setup. Figure analysis also requires an image-capable model. Back up your private `data/` before upgrading. See [third-party notices](THIRD_PARTY_NOTICES.md) for Poppler licensing and source access.

## Features and limits

- A shared reading workspace for the library, blank notes, reading cards and joint discovery, with saved-analysis progress and responsive layouts.
- From v0.4.0 portable Windows packages: stable-release checks and an explicit one-click update, checksum verification, restart checks and automatic program rollback. Personal data, virtual environments and installed Poppler are preserved.
- Read-only Zotero browsing, collection filters and direct original PDF access.
- On-demand paper chapters and terminology lessons with source snippets, formula rendering and PDF page navigation.
- Selectable PDF text, a personal glossary and contextual translation.
- Side-by-side figure explanations with optional region selection.
- Local caches/history and reading priorities based primarily on your research goals and paper content.
- Blank notes with optional paper links, autosave, revision conflict protection, Markdown/standalone HTML export and browser print-to-PDF. Reading cards separately store selections, user-initiated questions, conversations and editable summaries. Viewing/saving does not call a model; sending a card question or generating its summary does.
- Optional CAS/JCR journal data import: `.\.venv\Scripts\python.exe scripts/import_journals.py`. This downloads a pinned third-party dataset; it is not live official data, and SJR is not used as a replacement for JCR.

Chapter and terminology readers provide independently scrolling navigation and text, saved progress and expandable source coverage. Figure analysis shows the page and explanation side by side on wide screens, with independent scrolling and page arrows beside the image; narrow screens stack the panels. Selection actions appear vertically and move above the selection when space below is limited.

After a source update, use **Ctrl+F5** if the browser still displays old styles. Release ZIPs contain the version associated with their release; newer interface changes may first be available in the source repository. Back up private `data/` before updating.

## Updating

Open **软件更新** (Software update) at the top right. Automatic checks are cached for 24 hours and only contact this project's public GitHub Releases; they do not use your model key or send papers. Installation starts only after you click **立即更新**. Keep the terminal open while the launcher verifies, replaces and restarts the program. If replacement or the new server's startup check fails, it restores the old program. The last changed-program backup is retained under `.updates/last-backup/`; this is not a backup of your private data.

Versions v0.3.0 and earlier need one manual upgrade to a package with the updater: back up `data/`, extract the new package into a new directory, transfer `data/`, then run `setup.cmd`. The updater refuses Git checkouts, modified program files and source ZIPs without the release manifest. Changes to Python dependencies or the Poppler version require a manual upgrade; the UI explains this before stopping the old server. Finish active generation/search/save requests and save card edits first. No update alters the Zotero library.

Viewing cached results is free of model calls; generating, regenerating and uncached translation may use your paid API. Connection tests only check `/models`. Closing an analysis window cancels local work and disconnects the upstream request; provider-side cancellation and billing remain provider-dependent. Scanned PDFs have no OCR support. Source locations help verification but do not guarantee correct explanations.

## Your data

The server binds to `127.0.0.1` and has no login or multi-user isolation. Other users should run their own copy with their own Zotero library. Do not expose this service to the internet.

Settings and results live in local `data/`, which is excluded from Git. Model keys saved through the interface are encrypted using Windows DPAPI for the current user; discovery-service keys remain in plaintext. Re-save legacy model settings to migrate an old plaintext model key. Model-backed actions send relevant paper text or selected images to your configured provider. Back up `data/` privately before upgrading; your Zotero library requires its own backup. Never upload these directories with an issue.

## Contributing and licensing

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) and the issue templates. Tests do not require a paid model API. The original project code and documentation are [MIT licensed](LICENSE); bundled dependencies and third-party datasets retain their own terms. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
