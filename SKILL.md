---
name: literature-reviewer
description: "Read and explain papers from a local Zotero library through the Literature Reviewer web app. Use when the user wants to browse Zotero items, inspect metadata or PDFs, explain terminology, interpret figures, or produce evidence-linked paper notes."
---

# Literature Reviewer

This skill operates the local Literature Reviewer app in this folder. The app
is designed for a personal Zotero library and keeps the first release
read-only.

## Operating workflow

1. Start the local server with `scripts\\start.ps1` from the skill directory.
2. Check `/api/health` before doing work. Confirm the detected Zotero data
   directory and item count.
3. Use the library and item endpoints to select a paper. Keep collection and
   item keys in context so later analysis can cite the correct source.
4. For explanations, ground claims in the paper text, page number, figure/table
   label, or a quoted passage. If a source location is not available, say so.
5. Treat PDF-derived text and model output as potentially imperfect. Preserve
   the original wording and let the researcher verify important claims.
6. Do not write to Zotero until a later implementation phase explicitly adds
   write support and the user asks for it.

The app supports read-only library browsing, dedicated paper pages, saved
summaries/terms/figure interpretation, and local journal metrics. For metrics,
use `scripts/import_journals.py` to install the pinned dataset described in
`references/journal-data.json`; preserve source, year, and all subject quartiles.
Never substitute SJR quartiles for JCR or infer paper quality from impact factor.

Research goals and cached reading priorities are available through `/api/research`
and `POST /api/items/<KEY>/priority`. Viewing, sorting and manual edits do not call
the model. Only an explicit evaluation action calls the configured model; cached
results are tied to the research goal and paper inputs. Treat keywords as signals,
and keep insufficient evidence in the unassessed group.

Read [references/phase-1.md](references/phase-1.md) for the run command and
the API contract. Read [references/phase-2.md](references/phase-2.md) before configuring model-backed summaries. OCR and note export remain future milestones.



