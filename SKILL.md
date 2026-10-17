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

The current milestone supports read-only library browsing, metadata, opening
local PDFs, and page-by-page text extraction.

Read [references/phase-1.md](references/phase-1.md) for the run command and
the API contract. Read [references/phase-2.md](references/phase-2.md) before configuring model-backed summaries. Later milestones will add OCR, terminology, figure/table
interpretation, and note export incrementally.



