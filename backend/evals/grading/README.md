# Grading eval

Grades real exam cases with a provider and compares the points to the ones you gave.

1. Export cases from the app's dev server: "Export eval cases" link in the grading view. Save as
   `backend/evals/grading/cases.jsonl` (one `{"id", "expected", "request"}` per line).
   The file holds exam crops, so it is git-ignored. Never commit it.
2. Run from `backend/` with the provider's key in the environment:

   ```
   ANTHROPIC_API_KEY=... uv run python -m evals.grading.run_eval evals/grading/cases.jsonl
   GOOGLE_API_KEY=...     uv run python -m evals.grading.run_eval --provider google evals/grading/cases.jsonl
   OPENROUTER_API_KEY=... uv run python -m evals.grading.run_eval --provider openrouter --model vendor/model evals/grading/cases.jsonl
   ```

   `--model` defaults to the provider's default. Cases with a solution are graded against it, the others
   in `own_solution` mode. The report goes to `results/<date>-<provider>-<model>.md`.

Metrics (per basis):
- `exact`: share of cases where the points equal the expected points.
- `in_range`: share where the expected points lie in the model's `points_min..points_max`.
- `within_half` / `within_one`: share where the points are at most 0.5 / 1 away from the expected points.
- `mae`: mean absolute error in points.
- `calibration`: share of `certain` grades that are exact (should be near 1).
- Failures (e.g. provider errors) are counted per code and not scored.

## Real exams

Graded exam scans (the teacher's points as ground truth) with their solution PDFs, in `evals/grading/private/`
(git-ignored: exams, crops and transcriptions never get committed). Run from `backend/`; the key can live in `backend/.env`.

```
uv run python -m evals.grading.import_scans                 # -> private/cases.jsonl, coverage.md, contact-sheet.png
uv run python -m evals.grading.manual_cases                 # typed-out answers in private/manual/*.md -> private/manual-cases.jsonl
uv run python -m evals.grading.run_eval --model claude-haiku-5-5 --limit 5 evals/grading/private/cases.jsonl   # smoke
uv run python -m evals.grading.run_eval --model claude-haiku-5-5 evals/grading/private/cases.jsonl
```

The importer skips MC subtasks and excludes an exam whose printed points don't add up to the cover total
(`coverage.md` says why). Those exams can be typed out by hand into `private/manual/` instead; report their run
separately, since it measures transcription as well as grading. Both runs write the same report name, so rename the
second one (e.g. `...-transcribed.md`). Results and caveats: `docs/2026-11-26-grading-eval-handoff.md`.

To compare providers, run the same cases file with each and compare the reports (same prompt version).

Free tiers may use your inputs for training. Check the provider's terms before sending exam material.
