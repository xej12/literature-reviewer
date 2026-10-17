# Phase 2: structured paper summary

The detail pane now exposes a **生成论文解读** action. It sends the selected
paper's metadata, abstract, and the first part of its PDF text to an
OpenAI-compatible `/chat/completions` endpoint. The expected JSON fields are
research question, methods, findings, and limitations.

Configure a provider from the **模型设置** button in the top-right of the web
page. Fill in the API address, model name, and API Key, then save. The key is
stored locally in `data/settings.json` and is excluded from version control.

The equivalent environment configuration is still supported:

```powershell
$env:LITERATURE_REVIEWER_API_KEY = "your-key"
$env:LITERATURE_REVIEWER_BASE_URL = "https://api.openai.com/v1"
$env:LITERATURE_REVIEWER_MODEL = "gpt-4o-mini"
```

The API key is read only by the local server and is never returned by
`/api/model`. A local OpenAI-compatible server can be used by changing the
base URL and omitting the key only if that server accepts the configured
request without authentication.

The same model configuration powers the professional-term extraction action in
the paper detail pane. It returns at most eight terms with an explanation,
paper-specific context, and a page hint.

Summary, term, and page-level figure results are cached per Zotero item under
`data/analysis/`. Figure results use the PDF attachment key and page number as
their cache key, so opening a previously interpreted page does not call the
model again. The explicit “重新解析（消耗 Token）” button bypasses that cache.

The 图表解析 action renders one PDF page locally for preview and sends only
that page image to the configured OpenAI-compatible vision model. It returns a
short description, trends, takeaway, and caveats; the result is stored beside
the paper's other analysis results.

Users can choose **框选图表**, then drag over the PDF preview to include a
figure, caption, axes, and legend. The server crops the page image before
sending it to the model. Whole-page and region results have separate cache
keys; the saved-results dropdown reopens existing regions without a model
request. Regions use normalized coordinates so zooming the preview does not
change the crop.

HTML snapshots are labeled as webpages and opened as HTML, with scripts
sandboxed away from local settings APIs. A record containing no PDF offers
its original source webpage instead. Adding a PDF in Zotero and refreshing
the browser enables PDF reading and figure interpretation for that record.
Opening or viewing a cached result does not call the model. The modal includes
an explicit regenerate action for cases where the paper or prompt has changed;
that action is the one that consumes a new request.

Paper cards now open a dedicated detail page at `#/items/<ZOTERO_KEY>`.
Returning to the library preserves its current collection, search and scroll
position. Browser back/forward and direct detail links work without an extra
server route. Author lists show all names up to three, otherwise the first
three and the total count; details can expand to the complete list.

Library queries exclude Zotero's trash. Display duplicates are grouped before
search, collection filtering and result limits. Matching uses DOI fields,
DOIs in publisher URLs, or case/punctuation-normalized titles of at least 20
alphanumeric characters. Conflicting DOIs and ambiguous title matches remain
separate. Each group prefers an existing local PDF, then metadata completeness.
Search matches any member's title/abstract and collection membership matches
any member, while displaying the preferred record. Library and collection
counts reflect these groups. This affects only display; Zotero records and
per-item analysis files remain untouched. Grouping currently reads the full
local library, which is suitable for the present personal library; larger
libraries will need indexing alongside the planned pagination work.

`GET /api/library?q=&collection=&status=all&limit=100` returns a library
snapshot with active collections, preferred item records, per-item
`analysisStatus`, and progress totals. Status accepts `all`, `summary`,
`unread`, `terms`, or `figures`. Counts cover the full current search and
collection before status filtering and the display limit. "已解读" means a
saved paper summary exists; terms and figures are counted independently.
"已解析图表" means at least one saved figure result, not every figure in a
paper. These totals never call a model. Saving an analysis refreshes them.

Deleted collections are excluded from collection lists and item memberships.
Valid empty collections remain visible. The client can refresh manually,
checks when the window becomes active again, and polls every 30 seconds while
visible. Refresh preserves search and status filters and follows collection
renames. If the selected collection is deleted, the server falls back to the
whole library and the client explains the change. This refresh reads local
Zotero data; it does not initiate Zotero cloud synchronization or write to it.
