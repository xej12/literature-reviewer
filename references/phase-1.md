# Phase 1: Zotero library browser

This milestone intentionally reads the Zotero SQLite database without modifying
it. The server discovers the Windows data directory automatically and opens the
database read-only. The web UI is served at `http://127.0.0.1:8765`.

Start it from PowerShell:

```powershell
cd D:\codex\literature-reviewer
.\scripts\start.ps1
```

Useful endpoints:

- `GET /api/health` — detected Zotero version, data directory, and item count.
- `GET /api/collections` — collections and item counts.
- `GET /api/items?q=keyword&collection=COLLECTION_KEY` — paginated item list.
- `GET /api/items/ITEM_KEY` — metadata, creators, collections, and attachments.
- `GET /api/attachments/ATTACHMENT_KEY/text?page=1` — extract one PDF page as text.
- `GET /api/attachments/ATTACHMENT_KEY/file` — stream a local PDF in the browser.

The first implementation opens SQLite in read-only mode and falls back to an
immutable read view if Zotero briefly holds a lock. Restart the server after
substantial Zotero changes if the browser has not refreshed the library count.

PDF extraction is page-oriented and uses `pypdf`. Scanned pages without a text
layer are reported as empty; OCR and figure interpretation will be added in a
later milestone.
