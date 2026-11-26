# Grading eval on real graded exams — handoff

Runs on 2026-11-27, model `claude-haiku-5-5`, prompt version `2026-11-05.1`, no prompt tuning.
Reports: `backend/evals/grading/results/2026-11-27-anthropic-claude-haiku-5-5.md` (image answers) and
`...-transcribed.md` (typed-out answers). Inputs stay in `backend/evals/grading/private/` (git-ignored).

## Results

Expected = the teacher's printed points per subtask. `own_solution` = Haiku writes its own solution first and grades against it;
`solution` = Haiku grades against the official solution.

Headline, student answers as scan crops (6 exams, 134 text subtasks):

| basis | n | exact | within 0.5 | within 1 | in range | MAE | calibration |
|---|---|---|---|---|---|---|---|
| own_solution | 134 | 0.58 | 0.72 | 0.94 | 0.65 | 0.42 | 0.62 |
| solution | 134 | 0.71 | 0.82 | 0.97 | 0.72 | 0.28 | 0.71 |

Transcribed answers (separate, not part of the headline): exams the importer excluded, with the student's answers typed out
by Claude reading the scan pages, so it also measures the transcription (4 exams, 107 text subtasks):

| basis | n | exact | within 0.5 | within 1 | in range | MAE | calibration |
|---|---|---|---|---|---|---|---|
| own_solution | 107 | 0.45 | 0.61 | 0.90 | 0.52 | 0.56 | 0.49 |
| solution | 107 | 0.67 | 0.77 | 0.91 | 0.70 | 0.35 | 0.69 |

No provider failures in either run. The official solution beats self-solving in both, by 13 and 22 points of exact match.

## Coverage (aliases only)

- Imported: exam-01, -02, -03, -05, -10, -11. MC subtasks are skipped (graded without the LLM); exam-03 has 11 and
  exam-11 has 2 text subtasks without a case: no unique printed score matched, or the case was dropped (points above
  the pipeline max, or a region under 45pt).
- Excluded by the importer for a points-sum mismatch with the cover total: exam-04, -06, -07, -08, -09.
  All five went to the manual fallback; their typed-out sums equal the cover totals. exam-07 is all MC, so it gives no cases.
  5 manual entries were dropped (4 with no max points from the pipeline, 1 with points above the max).

## Caveats

- One student, 11 exams, about 240 text subtasks in total; per-exam numbers are too small to read anything into.
- The teacher's grade is the only ground truth; a different grader could differ by similar margins.
- The transcribed run mixes transcription error with grading error.
- One run each, no repeats, so run-to-run noise is unmeasured.

## Not done

- The one-sentence result in the project README (wording waits on the user).
- Open minor findings of the manual loader are in `docs/findings.md`.
