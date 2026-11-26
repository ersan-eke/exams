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
- `mae`: mean absolute error in points.
- `calibration`: share of `certain` grades that are exact (should be near 1).
- Failures (e.g. provider errors) are counted per code and not scored.

To compare providers, run the same cases file with each and compare the reports (same prompt version).

Free tiers may use your inputs for training. Check the provider's terms before sending exam material.
