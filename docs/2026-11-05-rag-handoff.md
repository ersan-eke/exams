# Phase 4, RAG "Ask" + study material: status and what's left

Written 2026-11-05. Plan (also the spec): `docs/superpowers/plans/2026-11-05-rag.md`. Earlier context: `docs/2026-11-04-mcp-handoff.md`.
Tests at the end: backend 341 passed, frontend 335 passed (43 files), `npm run type-check` clean, ruff clean.
Not yet done: `/code-review high` and `/security-review` on the branch `phase-4-rag` (uploads, a file route and a key header are touched).

## Done

- **Infra:** compose image `pgvector/pgvector:pg18`; one migration `a9f3c1d2e4b6` (extension `vector`, `documents`, `chunks` with a generated
  `tsvector` + GIN and a 384-dim HNSW cosine index, `jobs.kind`, `jobs.document_id`, `jobs.role` nullable). Dev volume kept: only the collation
  versions had to be refreshed (see CLAUDE.md).
- **Embeddings:** local `fastembed`, `paraphrase-multilingual-MiniLM-L12-v2` (`app/rag/embed.py`), no key anywhere. About 120 MB download on first use.
  Real-model check: the right page ranks first on a German exam PDF (sim 0.74), search 0.03 s, 8 chunks embedded in 1.3 s.
- **Material:** one PDF = one chapter (`documents`: kind slides|script|exercises, title, position, nullable `course_id`). `POST /api/documents`
  (sha256 dedupe, 100 MB cap), `GET/PATCH/DELETE /api/documents[/id]`, `GET /api/documents/{id}/file` (inline PDF, owner only). A PDF can be
  uploaded without a subject and filed later with PATCH (it then goes to the end of that subject). The worker reads text with the existing
  extractor, chunks per page (600 chars), embeds, and keeps the PDF in `STORAGE_DIR/documents/<id>/file.pdf`. A PDF without text fails as
  `scanned` and leaves no row.
- **Exam chunks:** the worker indexes account-owned subtasks that have no chunk yet while its queue is idle (`rag/index.py`), which covers uploads,
  sync, edits and existing data without touching request paths.
- **Search:** `rag/search.py`, vector + full-text merged with RRF, always scoped to user and subject. `POST /api/ask` (own key in `X-LLM-Key`,
  structured `{answer, cited}`, unknown cited ids dropped, per-user limiter, no LLM call when nothing is found). Adapters got an optional
  output model so Ask reuses all three providers (`grader.complete`).
- **Where to read:** `POST /api/materials/lookup` returns up to two pages (one per page) from the subject's material, also when a solution exists.
  The button "Where to read this" under each subtask in Results calls it on click.
- **Grading:** without a solution a signed-in request gets up to 3 excerpts (cap 1500 chars) as text (`rag/material.py`); with a solution nothing
  is added. Signed-in clients send `subject` and no reference images. Prompt version bumped.
- **MCP:** `find_tasks(query)` ranks by meaning and still text-matches unindexed subtasks.
- **Frontend:** `/ask` (subject, ordered chapters with rename/reorder/delete, multi-file upload, unfiled list, question + cited answer),
  `/material/:id?page=N` (the browser's PDF viewer in an iframe, prev/next chapter), "Add material" per subject in My exams.

## Not done

- Manual check, for you: sign in, add two chapter PDFs from My exams and one from Ask, ask a question, follow a citation to the page; press
  "Where to read this" in Results with and without a solution sheet. Not tried in a real browser: the iframe's `#page=N` in Chrome/Safari/Firefox.
- `MIN_SIM = 0.3` (`rag/search.py`) was chosen on two sample decks; tune it with real slides.
- The grading eval (`backend/evals/grading`) was not rerun against the new prompt block.
- No streaming for Ask; scanned slides are not read (no OCR); an exercise is not paired with its solution; the first grading request of a
  server process loads the embedding model (about 1-2 s).
- Eslint has 4 errors that predate this phase (`Sheet.vue`, `Modal.vue`, `GradingList.vue`, `grading.ts`).

## Decisions already made (don't revisit)

- Earlier handoffs still stand. Embeddings are local; the user's key is only used for the answer itself.
- Chunks hold no course id; scope comes from the owning document or exam, so filing a chapter later is one row update.
- The viewer is the browser's built-in one (no pdf.js); per-page PNGs are not rendered.
- Links under a subtask come from retrieval on click, not from the grading model.
