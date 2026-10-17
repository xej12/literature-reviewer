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
Opening or viewing a cached result does not call the model. The modal includes
an explicit regenerate action for cases where the paper or prompt has changed;
that action is the one that consumes a new request.
