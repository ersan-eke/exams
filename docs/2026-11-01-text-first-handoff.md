# Phase 2b, text-first grading inputs: status and what's left

Written 2026-11-01, after Phase 2b. Spec: `docs/superpowers/specs/2026-11-01-text-first-inputs-design.md`; plan: `docs/superpowers/plans/2026-11-01-text-first-inputs.md`.
Earlier context: `docs/2026-10-29-llm-grading-handoff.md`, `docs/2026-10-28-backend-foundation-handoff.md`.
Tests at the end: backend 236 passed, frontend 275 passed (37 files), `npm run type-check` clean, smoke 15/15 unchanged.
Full samples run (306 PDFs, `--no-debug`): 182 ok, 105 warn, 19 error, no crashes. All 19 errors are scanned pages (no OCR yet) or "no task headers found".

## Done

- **Points** (`backend/app/pipeline/structure.py`): more point sources are read (per-subtask totals in headers, "je N P",
  brackets, slash totals, MC rules stated in the intro) and cross-checked against the task total. `Task.mc_rule`
  (DB column `tasks.mc_rule`, migration) overrides the exam-wide MC rule. Report: `evals/text_first/points_report.py`.
- **Scripts folded into text** (`extract.py`, `fold_scripts`): `x_{1}`, `n^{2}` come out of the geometry instead of staying visual.
  Garbage folds are rejected (a run between two letters of one word) and mark the line as uncertain.
- **Visual only when text can't carry it** (`visual()` rewrite): two-dimensional math (big operators, fraction bars,
  brackets), figures, tables, code and uncertain scripts stay crops. Code keeps its indentation.
- **Optional docling pass** (`backend/app/pipeline/enrich.py`): formulas become `$LaTeX$` on the MLX engine, pictures
  (page furniture) are dropped, a digit guard rejects LaTeX that lost numbers. The worker calls `enrich(pdf, pages)`;
  CLI `--enrich`; `process(enrich=...)`. `mlx-vlm` is an optional dependency (darwin/arm64 only).
- **Editable max points** in the frontend (`StoredExam.pointOverrides`, `withPointOverrides`, `library.setPoints`),
  applied once when an exam loads.
- **Measurement script** `backend/evals/text_first/measure.py`; removed the dead `backend/app/ml_services/` stub.

## Numbers (306 sample PDFs; before = main 6dfd97e, after = this branch, no enrichment)

| | before | after |
|---|---|---|
| Subtasks without points, MC | 915 | 648 |
| Subtasks without points, other | 1637 | 1372 |
| Visual regions, subtasks (9583) | 59.5 % | 37.9 % |
| Visual regions, contexts (about 1940) | 71.0 % | 31.8 % |
| Estimated tokens per grading request (8364 requests) | 1018 | 836 |
| Seconds per exam (extract + group, no rendering) | 0.63 | 1.38 (machine busy) |

With enrichment, on 20 exams (incl. ana, linalg, numprog, theo), same exams without / with:
visual subtask 63.8 % (main) -> 42.0 % -> 38.2 %, context 63.3 -> 37.4 -> 28.3 %; tokens per request 1139 -> 947 -> 895;
seconds per exam 0.39 -> 0.57 -> 12.96 (Apple Silicon, MLX, model warm after the first exam).
Missing points do not change with enrichment. Tokens: text chars/4, each sent image ceil(w*h/750) at the 2.0 render scale
(144 dpi); a request is the subtask plus the task context that applies to it. Reproduce:
`uv run python -m evals.text_first.measure ../samples [--enrich] [--only name1,name2]` from `backend/`.

Missing points by remaining category (mc / other): per_tick without a solution key 241 / 0; task total only 257 / 1033;
nothing stated 135 / 241; "points" word inside the question 15 / 79; "je N" 0 / 19.

## Spot checks (by eye, crops against extracted text; rendered with `process()`, 7 exams)

- **20 regions that became text-only: 19 fine, 1 loss.** The loss: theo-endterm-2026 A1b has an overline on `L(M)`
  (complement) that the text drops, which changes the statement. One more (gad-endterm-2015 A1g) is complete but noisy:
  `(cid:3)` junk where checkboxes were, options and formulas intact.
- **10 still-visual regions: 8 really need the image** (tables/graph, scrambled big operator, subscripts a/b in
  `#a(p)`, piecewise function, fraction with cid glyphs, answer grid, ticked MC). **2 don't:** linalg-endterm-2024 A3a
  (text is complete, stays visual for an unmapped glyph) and linalg A9e#1 (a scissors cut mark alone).
- **Formulas: about 16 distinct converted formulas (24 regions, 15 regions viewed), 16/16 correct** against the crops
  (fractions, cases, sum, lim, 3x3 matrices, vectors, primes, `\|v\|^2`). Same as the 10/10 in Task 1. The equation number
  is dropped. Tables were not converted (see decisions), so there were no table checks.
- **10 random remaining no-points subtasks vs the exam text: 9 confirmed** (only a task total, or nothing, is printed).
  **1 possible miss:** gbs_IN0009_WS1920_RT_SOL A7d has a "1/2" marker next to the solution, probably 0.5 points.

## Not done

- **Exams uploaded before this phase need re-upload** to get the new points, text and visual flags (`visual` is null on
  old exams and counts as visual).
- **Formulas as LaTeX only on Apple Silicon.** On Linux/Docker `mlx-vlm` is not installed, enrichment is skipped, and formulas stay as they
  were (text if simple, crop if not). The CPU engine costs about 60 s per formula and is never used.
- **Tables stay crops.** Docling got 1 of 3 right.
- **Overlines:** a short bar over a text line is now visual; longer bars or bars with text above are not detected. `(cid:N)` glyphs stay in some texts.
- **Unneeded images remain:** scissors cut marks as their own region, and a few complete texts flagged for an unmapped glyph.
- **Points still missing:** 648 MC (241 are per-tick MC with no solution key, so no per-subtask value can be derived) and 1372 other.
  Task-total-only cases are real: the exam prints nothing per subtask (the user can set points in the UI).
  Solution-sheet markers like "1/2" are not read as points.
- Deferred points rules: bracket totals used once are dropped; "2+2=4" without a unit is rejected; only the first sum match
  is tried; intro-wide values can feed the two-value split; points regexes are not word-bounded; with a solution-only key a
  single-answer question gets one tick's points (override it in the UI).
- Deferred extraction: the fraction-bar rule fires on fill-in underlines; the vertical-rule rule has no minimum height;
  code with side rules is visual; prose between code lines is indented; Eidi-2017 t1 (b) place-value alignment is lost;
  the 4-identical-token rule rejects spaced numbers like "1 0 0 0 0"; the digit guard is a multiset check.
- Deferred enrichment: no timeout on docling; a hard MLX crash would block the job.
- **Max points of old attempts change:** the even split under a per-tick rule is gone, a per-tick question is worth its
  correct boxes (or `McRule.single` for a single answer), and the frontend even split needs a share that is a multiple of 0.5. Intended.
- **Docling LaTeX can translate or misspell German words inside `\text{}`;** the digit guard does not catch letters.
- **Enrichment runs on the first attempt only;** a crash-retry skips it (the crash may have been docling). No docling timeout.
- Deferred frontend: an invalid typed point value stays visible; clearing a value deletes the override without a hint;
  `planGrading` reference library ignores overrides.
- Smaller items: `.superpowers/sdd/2026-11-01-text-first-inputs/progress.md` ("minor (deferred)").
- **Step for the user (Apple Silicon):** `uv sync`, re-upload one exam, grade a subtask with a formula and check the
  request sent text, not an image. For a new exam type, run `uv run python -m evals.text_first.measure`.

## Decisions already made (don't revisit)

- Decisions in the earlier handoff docs and the spec still stand.
- Formulas only from docling (CodeFormulaV2 on the MLX engine), tables off: 1 of 3 tables was right, formulas 10/10 in Task 1 and 16/16 here.
- `mlx-vlm` is a platform-marked optional dependency (darwin/arm64) and enrichment is skipped when it can't import.
  This deviates from the spec's "no new runtime dependency" because the user asked for formulas as text.
- `valid_latex` also rejects unbalanced `\left`/`\right`, repetition runs and inner `$`; the digit guard rejects LaTeX that lost digits.
  Rejected formulas fall back to crops.
- Docling "pictures" are page furniture: dropped, never used to make a region visual or not.
- A script run inserted between two letters of one word is rejected as a fold and marks the line uncertain, so those regions stay visual.
- Two-dimensional math, tables, figures and uncertain scripts stay visual: a crop beats scrambled text.
- `Task.mc_rule` (column) overrides `ExamStructure.mc_rule`; the frontend `mcPoints` uses `task.mc_rule ?? attempt.mcRule`.
- Point overrides are applied once at exam load (`withPointOverrides`), not as a `maxPoints` parameter.

## Where things live

- `backend/app/pipeline/`: `structure.py` (points rules, visual), `extract.py` (`fold_scripts`, `Line`), `enrich.py` (docling), `__init__.py` (`process`).
- `backend/evals/text_first/`: `points_report.py`, `measure.py`. Tests: `backend/tests/test_{points,scripts,visual,enrich}.py` and the smoke golden `backend/tests/pipeline_smoke.json`.
- `frontend/src/stores/library.ts` (`setPoints`, `withPointOverrides`), `frontend/src/lib/grading.ts` (`maxPoints`, `mcPoints`).
