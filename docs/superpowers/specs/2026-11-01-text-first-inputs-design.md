# Phase 2b — Text-first grading inputs

Branch `phase-2b-text-first`. Plan: `docs/superpowers/plans/2026-11-01-text-first-inputs.md`.

## Why

LLM grading (Phase 2) sends question, solution and answer crops as images. Images cost far more tokens
than text, and much of what is sent as an image is really text the pipeline could hand over faithfully.
Separately, many subtasks have no point value even though the exam states it, so they can't be graded
properly. Goal (the user's words): *whenever a text representation is possible, send text; send images
only for what can't be text — figures, plots, drawings, handwriting.* And: *the points of every subtask
should be derivable from the exam* — per subtask, from the task header, from a total for an MC block
divided by its questions, from the cover page — in any wording (Punkte, points, credits, P, …).

## Measured starting point (306 sample PDFs, after the 2026-10-31 fixes)

- 915 of 1,629 MC subtasks and 1,637 of the other subtasks have no point value. Seen causes include a
  "/21" notation ("Kurz und Knapp /21"), an MC header total that doesn't split into half-point steps
  (18 P over 15 questions), points only in a cover-page table, and wordings the regexes don't know.
- Region `visual` flag (added 2026-10-31): 59 % of subtask regions and 69 % of context regions are
  flagged visual. Many only because of one monospace or math-font token (an IP address, "→") whose text
  extracts correctly — the font rule is too blunt.
- Sub/superscripts are flattened: "2²" becomes "22", "x₀" becomes "x 0" or a separate "0 0" line.
- docling 2.144 is installed but unused (`app/ml_services/layout_analyzer.py` is a dead stub).

## Goals

1. **Points always derived when the exam states them.** Every subtask gets a point value whenever the
   exam determines it, from any of: printed subtask points; inline notes ("e)* 2 Punkte: …"); the task
   header; an MC block total divided over its questions (with exceptions noted); a cover-page points
   table; the exam total minus known tasks. Any unit word or notation: Punkte/Punkt/Pkt/P, points/pts,
   credits, marks, "/21", "[3]", "(3)". The readings are cross-checked (subtask sum vs task header vs
   cover/total) and the consistent one wins; a contradiction is reported as an issue, as today.
   Subtasks still without points afterwards must be ones where the exam really states nothing (verified
   on a sample); they keep the 1-point verdict fallback from 2026-10-31.
   Patterns seen in the samples that the rules must cover (German + English wording; the arithmetic is
   language-independent): header sums in subtask order ("2P+2P+2P+3P=9P"), "je 1P=4P" / "N points each",
   inline notes ("a)* 1.5 Punkte:"), an MC rule stated in the task intro ("Single Answer mit 1 Punkt wenn
   richtig … 0 Punkten sonst"), per-tick scoring ("1 Punkt pro richtigem und -1 Punkt pro falschem Kreuz"),
   and scoring schemes ("Richtige Antwort: 1 Punkt • Falsche Antwort: -1 Punkt • Keine Antwort: 0").
   **Two-value split (user's rule):** when a task's total T, its question count N and exactly two stated
   point values p1 < p2 determine a unique split (n2 = (T − N·p1)/(p2 − p1) is a whole number in 0..N), the
   first N − n2 questions get p1 and the last n2 get p2. Three or more values or no total: not guessed.
   **MC rule per task:** a rule sentence applies to the task it stands in (task intro), else the exam's cover
   rule applies. `Task.mc_rule` (optional) overrides `ExamStructure.mc_rule`.
   **Per-tick tasks:** a question's maximum is its number of correct boxes × points per right tick; known
   from an answer key or attached solution, otherwise shown as "depends on the key" — never an even split.
   No LLM is used for points (user's decision).
5. **The user sets points last.** In the grading view, each subtask's points are editable ("set points"
   when missing); the value is stored on the exam (`StoredExam.pointOverrides`) and wins over every
   derived value, for all attempts of that exam.
2. **Faithful text.** The pipeline's texts (subtask, context, solution, MC options) carry what the print
   shows, in a form an LLM reads well:
   - sub/superscripts from glyph geometry (smaller, raised/lowered): `2^{2}`, `x_{0}`, `e^{-x}`;
   - display and inline formulas from docling's formula model (CodeFormulaV2) as LaTeX in `$…$`;
   - tables from docling's table structure as Markdown tables;
   - code keeps its line breaks and indentation;
   - Unicode symbols (→, ≤, ∈) stay as they are.
3. **`visual` means "the text can't carry it".** A region is visual only if it contains content that no
   text form above captured: pictures/plots/diagrams, drawn answer areas meant for sketches, handwriting
   (ink), formulas or tables the models failed on, unreadable glyphs. Fonts alone no longer decide.
   Same errs-towards-visual principle: when unsure, visual.
4. **Grading sends the least that is faithful.** No frontend rule change is expected beyond what exists
   (crops only for visual regions, no duplicate crops); the gain comes from better text and fewer
   visual regions.

## Non-goals

- OCR of scanned exams or of handwritten answers (still unsupported / sent as images).
- Changing what the student sees: crops in the exam UI stay as they are; the new texts are for the LLM.
- A re-process button: improved structures apply to exams uploaded after this phase (the user re-uploads).
- An LLM call at upload time, or any LLM call to read points.

## Constraints

- Pipeline changes follow CLAUDE.md: smoke check on every change, `--update` only for intended changes,
  the full `samples/` run before merging, with before/after numbers in the handoff.
- docling models run in the background worker (uploads are already async jobs). Its cost is measured
  first: model download size, seconds per exam on this machine. If formula/table enrichment makes a
  typical exam take more than ~60 s to process, it is limited to the regions that need it (only regions
  the cheap rules leave visual), and if that is still too slow, the phase falls back to the geometry
  rules only (goal 2's first bullet) and the measurement goes in the handoff.
- docling output is mapped onto the pipeline's own regions by page + bbox overlap; the pipeline's task/
  subtask structure stays the source of truth.
- Model output is untrusted text: LaTeX that doesn't parse (unbalanced braces/`$`, repetition) is
  dropped and the region stays visual.
- No new runtime dependency beyond docling's own model weights (downloaded once, cached; never committed).
- Exams processed before this phase keep working unchanged (missing fields = old behaviour).

## Acceptance (measured on all samples, reported in the handoff)

- Missing-points count before/after, by category; a manual check of 20 remaining cases that the exam
  states nothing for them.
- Share of visual regions before/after; a visual spot-check of 20 newly text-only regions (nothing lost)
  and 20 still-visual ones (really need the image).
- 30 converted formulas and 10 tables checked by hand against the crop; error rate reported.
- Estimated tokens per grading request before/after (images ≈ their pixel-based token cost, text ≈
  chars/4), averaged over the samples' subtasks.
- Processing time per exam before/after.
- All existing tests green; new behaviour covered by unit tests on the extraction rules.

## Left to the builder

- The exact geometry thresholds for sub/superscripts, and how merged lines are re-joined.
- How docling items are matched to regions (overlap threshold) and how converted text replaces the
  raw lines inside a region's text.
- The order of points-derivation rules and the cross-check algorithm, as long as each rule has tests from
  real sample wordings.
- Removing the dead `app/ml_services/layout_analyzer.py` stub.
