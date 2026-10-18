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

## On-demand deep reading

Open `GET /api/items/<KEY>/deep-reading` to inspect PDF coverage and cached
chapters for free. Only call `POST /api/items/<KEY>/deep-reading` with
`{"section":"overview|methods|formulas|evidence|limits","force":false}`
when the user explicitly requests chapter generation. Viewing a saved chapter
must not call a model. Do not generate all chapters automatically or use paid
model calls for software tests. The website provides this same workflow.

Use `scripts/deep_reading.py` for the application teaching contract. Distinguish
paper facts, background teaching and inference. Source IDs resolve to PDF page
order and exact extracted text; they verify location, not semantic correctness.
Show missing or partial text coverage. Never invent missing formula symbols.
Existing summaries remain in the old cache and can be viewed alongside deep
reading. New versioned chapter caches live in ignored `data/deep-reading/`.

## Terminology and selection translation

Use `GET /api/terminology` to read the shared personal glossary for free.
`POST /api/terminology` saves an explicitly supplied `term`, `translation` and
optional domain `note`; never claim that model-generated entries are vetted
terminology. The initial user-confirmed preference is coronagraph → 日冕仪.
Glossary rules apply to future chapter, terms and figure generation. Do not
silently regenerate cached content after a correction.

The web app supports manual selection translation and original-layout PDF
selection via locally bundled Mozilla PDF.js. `POST /api/items/<KEY>/translate`
accepts `text`, `context` and optionally owned `attachmentKey`/`page`. Exact
glossary hits are local; other selections may call the configured model when
not cached. Invoke it only for an explicit translation request, never merely
because text is selected. Reuse per-paper translation caches, require an
explicit action to translate again, and mock all model calls in software tests.
See [translation research](references/translation-research.md) for project
comparisons, licensing and current limitations.

## On-demand concept lessons

`GET /api/items/<KEY>/term-reading?term=<term>` opens saved lessons and source
coverage for free. Only an explicit request to generate a concept lesson may
call `POST /api/items/<KEY>/term-reading` with `term`, `force` and `repairOnly`.
Never generate every term automatically. Reopening lessons and local repair
must reuse existing data without model calls. `repairOnly:true` always forbids
model calls, even when there is no saved draft.

Use `scripts/term_reading.py` for term-specific teaching and evidence selection.
Explain prerequisites, mechanisms, paper-specific uses, teaching examples,
confusable concepts, limits and self-check questions. Keep background teaching
separate from paper evidence; lexical matches alone do not establish usage.
Cache each concept independently in ignored `data/term-reading/`, retain source
and glossary versions, and keep previous successful lessons on failed retries.



