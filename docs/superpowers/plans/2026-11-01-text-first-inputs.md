# Text-first Grading Inputs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every subtask gets the point value its exam states, and the pipeline hands the LLM faithful text
(sub/superscripts, LaTeX formulas, Markdown tables, code with layout) so that only true pictures, sketches
and handwriting remain images.

**Architecture:** Three layers in the existing pipeline (`backend/app/pipeline/`). (1) Points: more
derivation rules + a cross-check in `structure.py`. (2) Text fidelity in `extract.py`: glyph geometry folds
sub/superscripts into their line (`x_{0}`), code keeps indentation. (3) Optional enrichment in a new
`enrich.py`: docling finds formulas/tables/pictures; formulas become `$LaTeX$`, tables Markdown; they replace
the covered raw lines *before* grouping, so grouping, texts and `Region.visual` work on the improved lines.
`visual()` is rewritten to mean "something the text can't carry".

**Tech Stack:** Python 3.13, pdfplumber, docling 2.144 (CodeFormulaV2, TableFormer), pydantic, pytest; uv only.

**Spec:** `docs/superpowers/specs/2026-11-01-text-first-inputs-design.md`

## Global Constraints

- Pipeline changes: `uv run python -m app.pipeline.smoke` after every change; `--update` only for intended
  changes; full `uv run python -m app.pipeline.cli ../samples` before merging, before/after numbers in the handoff.
- Smoke and CLI stay fast and model-free by default (enrichment off); the worker enables enrichment.
- Enrichment budget: a typical exam must process in ≤ ~60 s with enrichment; else enrich only pages that still
  have visual regions after the cheap rules; if still too slow, skip Task 5 and record the measurement.
- Model output is untrusted: LaTeX failing validation is dropped and the region stays visual.
- When unsure, a region is visual (a missing figure costs a grade, an extra crop only tokens).
- No new runtime dependency besides docling's model weights (cached, never committed). Never commit PDFs/crops.
- Exams processed before this phase keep working (missing fields = old behaviour).
- `Line`/`Region` additions are optional fields with defaults; the stored `ExamStructure` stays backward-compatible.
- Deliberate simplifications carry a `shortcut:` comment.

## Review Focus

- `a)*`, `1.2*`, footnote stars and MC labels must survive script folding unchanged, or subtask detection breaks. → Task 3.
- Printed subtask points must never be overwritten by a derived share; contradictions become issues. → Task 2.
- docling missing, failing or offline: processing still succeeds without enrichment (logged), never a failed upload. → Task 5.
- Garbage LaTeX (unbalanced braces, `\quad` repetition): dropped, region stays visual. → Task 5.
- A region that is only an empty sketch grid / plot axes (e.g. "sketch the spline") stays visual. → Task 4.

---

### Task 1: Measure docling (spike, no app code)

**Files:** none in `app/`. Append results to the "Measurements" section at the end of this plan.

- [ ] **Step 1:** In a scratch script under `$CLAUDE_JOB_DIR/tmp` (or `/tmp`), convert 5 samples with docling
  (`PdfPipelineOptions(do_formula_enrichment=True, do_table_structure=True)`, see Context7 `/docling-project/docling`):
  `numprog/numprog-2026-endterm.pdf`, one `ana/`, one `linalg/`, one `theo/`, one `grnvs/` exam.
- [ ] **Step 2:** Record: first-run model download size, seconds per exam (warm), number of formula/table/picture
  items, and for 10 formulas the LaTeX next to the crop (correct / wrong).
- [ ] **Step 3:** Record the decision with the spec's rule: full enrichment / pages-with-visual-regions only / skip Task 5.
  Commit the plan update: `git commit -m "Plan: docling measurements"`.

### Task 2: Points always derived

**Files:** Modify `backend/app/pipeline/structure.py` (and `meta.py` only if wording helpers live there).
Create `backend/evals/text_first/points_report.py`. Test: `backend/tests/test_points.py`.

**Interfaces:**
- Produces: `points_report(root: Path) -> dict[str, list[tuple[str, str, str]]]` — category → [(exam, task, subtask)]
  for subtasks still without points, used again in Task 6. CLI: `uv run python -m evals.text_first.points_report ../samples`.

- [ ] **Step 1:** Write `points_report` (runs `group(extract(pdf))` over all samples, no rendering). Run it; read
  ≥ 3 PDFs per category and write each category with its real wording into the task report (e.g. "/21 after the
  title", "MC header total not a half-step split", "cover-page points table", "je N Punkte", "marks").
Rules required by the spec (in addition to what Step 1 finds): header sums in order (`test_header_sum_in_order`:
"Aufgabe 6 2P+2P+2P+3P=9P" → 2,2,2,3), "je 1P=4P" (`test_je_each_with_total`), the two-value split
(`test_two_value_split_from_end`: total 8, 6 questions, "1 Punkt" and "2 Punkte" stated → [1,1,1,1,2,2];
`test_two_value_split_not_unique_stays_open`: values that don't divide → no points, issue), MC rule per task from
the task intro (`test_task_level_mc_rule`: grnvs "Single Answer … 1 Punkt wenn richtig … 0 Punkten sonst" →
`Task.mc_rule` all_or_nothing, subtasks 1 P), per-tick tasks (`test_per_tick_max_is_correct_boxes`: with an answer
key → max = number of correct boxes × right; without key → points None and an issue "depends on the key", never
total/N), scoring scheme lists (`test_scoring_scheme_list`: eidi "Richtige Antwort: 1 Punkt • Falsche Antwort: -1
Punkt" → per_tick). Model: `Task.mc_rule: McRule | None = None` in `models.py`; frontend `Task.mc_rule?` in
`types/exam.ts`, and the frontend's `mcPoints` uses `task.mc_rule ?? attempt.mcRule`.

- [ ] **Step 2: Failing tests**, one per rule found, each with the real sample wording, e.g.:
  `test_slash_total_in_title` ("Kurz und Knapp /21" → task points 21), `test_points_each` ("je 2 Punkte" /
  "2 points each" → every subtask 2), `test_cover_table_points` (cover "Aufgabe 1 2 3 / Punkte 10 8 12" →
  task points), `test_marks_unit`, `test_mc_total_split_without_half_steps` (only if the sample PDFs show equal
  non-half-step splits are really meant — otherwise test that it stays an issue), and
  `test_printed_points_never_overwritten` (printed subtask points + a contradicting header → printed kept, issue raised).
- [ ] **Step 3:** Implement the rules and a cross-check that prefers the reading where subtask sum = task header
  = cover/total share; record a contradiction as an `Issue` as today.
- [ ] **Step 4:** `uv run pytest tests/test_points.py -v` → PASS; smoke; inspect every CHANGED entry, `--update`
  only if all changes are improvements; full-samples before/after missing-points count in the report.
- [ ] **Step 5: Commit** `git commit -m "Pipeline: derive subtask points from every stated source"`

### Task 3: Sub/superscripts as text

**Files:** Modify `backend/app/pipeline/extract.py`. Test: `backend/tests/test_scripts.py`.

**Interfaces:**
- Produces: `fold_scripts(raw_lines: list[dict]) -> list[dict]` — takes pdfplumber `extract_text_lines(return_chars=True)`
  dicts of one page, returns them with script glyphs folded into their base line as `^{…}` / `_{…}` and
  script-only lines removed. Used inside `extract_page` before `Line`s and `Word`s are built, so subtask texts,
  context texts, solution texts and MC option texts all get it.

- [ ] **Step 1: Failing tests** (synthetic char dicts): `test_superscript` ("2" + raised small "2" → `2^{2}`),
  `test_subscript_on_own_line` (base "(x , y )" + lower small line "0 0" → `(x_{0} , y_{0} )`),
  `test_multi_char_script` (`e^{-x}`), `test_labels_untouched` (`a)*`, `1.2*`, `(a)` unchanged),
  `test_footnote_star_untouched`; plus sample test `test_numprog_3a_subscripts` (task 3 a) text contains `x_{0}`).
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement: a glyph is a script if its size < 0.8 × the base size of the
  nearest same-row glyphs and its baseline is shifted up (superscript) or down (subscript) by ≥ 15 % of the base
  size; attach to the base glyph immediately to its left; a lone `*` right after a label is not a script.
- [ ] **Step 4:** Tests PASS; smoke (texts change, structure must not: tasks/subtasks/points/mc counts identical);
  `--update` if only expected fields changed.
- [ ] **Step 5: Commit** `git commit -m "Pipeline: keep sub/superscripts as ^{} and _{} in extracted text"`

### Task 4: `visual` means "the text can't carry it"; code keeps its layout

**Files:** Modify `backend/app/pipeline/structure.py` (`visual()`, `text_in()`), `backend/app/pipeline/extract.py`
(`Line.converted: bool = False`, set by Task 5). Test: `backend/tests/test_visual.py`.

**Interfaces:**
- Consumes: `fold_scripts` (Task 3). Produces: `Line.converted` (lines produced by enrichment; `visual()` ignores
  graphics inside a converted line's bbox).

- [ ] **Step 1: Failing tests** in `test_visual.py`: `test_monospace_word_is_text` (one Inconsolata IP address → not
  visual), `test_math_symbol_font_is_text` ("→" in LMMathSymbols → not visual), `test_code_is_text_with_indent`
  (code lines → not visual, and `text_in` keeps indentation as leading spaces from x0), `test_garbled_glyphs_visual`
  ("(cid:12)" → visual), `test_sketch_grid_visual` (grid of lines + axes → visual), `test_converted_table_is_text`
  (a `converted` line covering a table grid → not visual); update the existing font/code/subscript tests to the new
  meaning; keep `test_numprog_flags` but 3a and 3b become `False` (subscripts folded, code as text) while 3d stays `True`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement: drop the font and code triggers and the size-scripts trigger;
  keep images, curves, small rect/line count ≥ 6 (excluding graphics inside converted lines), garbled glyphs;
  `text_in` indents code-looking lines (`CODE_RE`) by `round((ln.x0 - region_left) / (0.5 × ln.size))` spaces.
- [ ] **Step 4:** PASS; smoke; full-samples share of visual regions before/after into the report.
- [ ] **Step 5: Commit** `git commit -m "Pipeline: visual only when text can't carry the content; code keeps indentation"`

### Task 5: docling enrichment (formulas → LaTeX, tables → Markdown, pictures)

Skip with a ledger ruling if Task 1 decided "skip Task 5".

**Files:** Create `backend/app/pipeline/enrich.py`. Modify `backend/app/pipeline/__init__.py` (`process(..., enrich=False)`),
`backend/app/worker/main.py` (call `enrich_pages` between `extract` and `group`), `backend/app/pipeline/cli.py`
(`--enrich` flag). Test: `backend/tests/test_enrich.py`.

**Interfaces:**
- Produces: `@dataclass Enriched(page: int, bbox: tuple[float, float, float, float], kind: Literal["formula", "table", "picture"], text: str | None)`
  (bbox in PDF points, top-left origin like `Line`); `find_items(pdf_path, pages: set[int] | None = None) -> list[Enriched]`
  (docling call, the only place that imports docling); `valid_latex(s: str) -> bool`;
  `enrich_pages(pages: list[Page], items: list[Enriched]) -> None` — for each formula/table item with valid text,
  removes the page's body lines whose center lies in the item bbox and inserts one `Line(converted=True)` with text
  `$…$` (formula) or the Markdown table; pictures are appended to `page.graphics` as kind `"image"`.
  `enrich(pdf_path, pages) -> None` = find + apply, catching every exception (log type only) so processing never fails.

- [ ] **Step 1: Failing tests** (fake items, no docling needed): `test_formula_replaces_lines`,
  `test_table_becomes_markdown_and_region_text`, `test_picture_makes_region_visual`,
  `test_invalid_latex_dropped` (unbalanced `{`, `$` count odd, ≥ 4 repeated `\quad`), `test_enrich_failure_is_swallowed`
  (`find_items` raises → `enrich` returns, pages unchanged); one integration test on `numprog-2026-endterm.pdf`
  marked skip when docling models aren't cached.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement per Task 1's decision (all pages, or only pages with visual
  regions after a first cheap `group`). **Step 4:** PASS; time 5 exams with enrichment into the report.
- [ ] **Step 5: Commit** `git commit -m "Pipeline: docling enrichment for formulas, tables and pictures"`

### Task 5b: Editable points in the grading view

**Files:** Modify `frontend/src/types/attempt.ts` (`StoredExam.pointOverrides?: Record<string, number>`),
`frontend/src/lib/scoring.ts` (`maxPoints(task, s, overrides?)` — override first), its callers
(GradingRow, LlmSummary, lib/grading.ts planGrading, scoring totals), `frontend/src/stores/library.ts`
(`setPoints(examId, subtaskId, points | null)`), `frontend/src/components/results/GradingRow.vue`.
Test: `scoring.spec.ts`, `GradingRow`/`GradingList` specs, `library.spec.ts`.

- [ ] **Step 1: Failing tests:** `maxPoints` returns the override over printed/derived points; `setPoints` persists
  and `null` removes the override; GradingRow shows "2 P" as an editable number input (`aria-label="Max points"`)
  and "set points" when missing; changing it updates the row's PointsPicker max and the LLM card scale (verdict
  mode turns into points), and later attempts of the same exam see it.
- [ ] **Step 2–4:** implement, run `npx vitest run` + `npm run type-check`. **Step 5: Commit**
  `git commit -m "Grading: editable max points per subtask, stored on the exam"`

### Task 6: Measure, clean up, document

**Files:** Create `backend/evals/text_first/measure.py`. Delete `backend/app/ml_services/layout_analyzer.py`
(and the package if empty, after `grep` shows no imports). Create `docs/2026-11-01-text-first-handoff.md`;
modify `docs/roadmap.md` (status), `CLAUDE.md` (handoff pointer).

**Interfaces:**
- Consumes: `points_report` (Task 2), `enrich` (Task 5). Produces: `measure(root: Path, enrich: bool) -> dict` with
  missing points, visual share (subtask/context), estimated tokens per request (text chars/4 + images at
  ⌈w·h/750⌉ tokens each), seconds per exam.

- [ ] **Step 1:** Run `measure` on `main`'s pipeline (git stash/worktree) and on this branch, enrichment on for 20 exams.
- [ ] **Step 2:** Spot checks for the handoff: 20 newly text-only regions and 20 still-visual (view crops),
  30 formulas and 10 tables against their crops, 20 remaining no-points cases against their PDFs.
- [ ] **Step 3:** Full `uv run pytest`, `npx vitest run`, smoke, full samples run. Handoff (done / not done /
  decisions / numbers), roadmap, CLAUDE.md. Commit `git commit -m "Docs: text-first inputs handoff"`.

## Measurements

Docling 2.144, `PdfPipelineOptions(do_ocr=False)`, macOS, `device=auto` (CPU-bound, ~390% CPU), 5 exams.
Setup note: `backend/.venv` had a broken `cv2` (empty namespace package, `cv2.setNumThreads` missing) so table
structure crashed; `uv pip install --reinstall opencv-python-headless` fixed it (venv only, no repo change).

**Model download (HF cache, first run):** +610 MB (`CodeFormulaV2`, the formula model). Layout (heron, 164 MB) and
TableFormer (`docling-models`, 342 MB) were already cached.

| Exam | Pages | (a) layout s | (b) + tables s | (c) + formulas s | formulas | tables | pictures |
|---|---|---|---|---|---|---|---|
| numprog-2026-endterm | 12 | 2.2 | 3.3 | **349.7** | 7 (4 pages) | 0 | 10 |
| ana_2024_Main | 17 | 3.9 | 4.4 | not run (see below) | 21 (8 pages) | 0 | 77 |
| linalg-endterm-2024 | 11 | 2.4 | 2.7 | not run | 9 (5 pages) | 0 | 45 |
| theo-endterm-2026 | 20 | 4.7 | 4.8 | not run | 2 (2 pages) | 0 | 80 |
| grnvs_endterm_2024 | 16 | 4.3 | 7.2 | not run | 0 | 3 | 30 |

Formula enrichment costs about 50-70 s per formula, not per page. Single-page runs with `page_range`: numprog p9 (1 formula)
68.9 s, theo p6 (1) 71.3 s, linalg p6 (3) 255.2 s, ana p3 (10) 698.7 s. The remaining (c) runs were skipped because
numprog alone already decides it (ana would be ~20 min). Counts come from the layout labels (identical in all configs).
Layout + tables alone is cheap (2-7 s per exam).

**Formula accuracy (10 LaTeX strings vs crops, numprog p5/7/9/10 and ana p3): 10/10 correct**, including `\frac`, `\int_0^t`,
`\sum_{k=1}^n`, `\lim_{x\to0}`, `pmatrix`, `\nu`. Only flaw: the equation number "(4.1)" is dropped.

**Table accuracy (grnvs 2024, 3 of 3 tables):**
- p4 probability table: correct (caption merged into the Markdown, `A` calligraphic lost, fine).
- p8 four routing tables: wrong structure; the four side-by-side tables are merged into one grid with "(a) R1 - ..." headers,
  rows e/f collapsed into one cell, subscripts flattened (`N1`).
- p10 hex dump: wrong; columns misaligned/merged (`00 09`, `b0` glued to the row label), header row lost.
Tables are right for simple single grids and unreliable for multi-table or monospace layouts; no table crop should be dropped on docling's say-so alone.

~~**DECISION (superseded by the MLX re-measurement below): skip Task 5.** Even limited to the formula pages, enrichment costs ~1 min per formula (numprog: 350 s for 7 formulas,
a typical exam has 7-21), far above the 60 s budget, so neither "full" nor "pages with visual regions only" fits; the formula
quality (10/10) is good enough that a faster backend (GPU/MPS, or a smaller formula model) would be worth revisiting later.

**MPS / MLX re-measurement (follow-up).** `AcceleratorOptions(device=MPS)` alone fails: the CodeFormulaV2 transformers engine
supports only cpu/cuda/xpu ("MPS is not supported by this model"), and `device=auto` silently runs it on CPU (the slow path above).
The fast path is the MLX engine: `pipeline_options.code_formula_options.engine_options = MlxVlmEngineOptions()` (from
`docling.datamodel.vlm_engine_options`) plus `uv add mlx-vlm` (Apple Silicon only; installed into the venv only for this test,
no pyproject/lock change). Tables off, formulas on, warm:

| Run (MLX, tables off) | formulas | seconds |
|---|---|---|
| numprog p9 | 1 | 4.3 |
| linalg p6 | 3 | 5.4 |
| numprog full exam (12 p) | 7 | 11.0 |
| linalg full exam (11 p) | 9 | 22.1 |
| ana full exam (17 p) | 21 | 36.9 |

About 1.5-3 s per formula, a 15-30x speedup over CPU. Accuracy on the 4 re-checked formulas: 3 correct (identical LaTeX to the CPU run),
1 truncated (linalg p6 `f(...) = det(...)` lost its closing `\right ) .`; the CPU run had it, so MLX is slightly less reliable on long matrix formulas).

**DECISION: full enrichment, formulas on MLX with tables off** (typical exam 11-37 s, under the 60 s rule; no need to restrict to
pages with visual regions; tables stay off because only 1 of 3 was correct). Caveats for Task 5: MLX works on Apple Silicon only,
so Task 5 must make enrichment optional with a fallback to no formula LaTeX when `mlx_vlm` is missing (CPU transformers costs
~60 s per formula and must not be used), and the result should be treated as a hint, since long matrix formulas can come out truncated.
