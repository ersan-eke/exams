# Anki export

On a Subject's statistics page (`/statistics/<Subject>`), **Export weak questions to Anki** downloads `<Subject>.apkg`.
No LLM and no key are involved.

## What is in the deck

- One note per subtask whose **latest** graded score is strictly below **60 %** (`?below=0..1` on `GET /api/subjects/<id>/anki` changes the threshold).
  Subtasks never attempted are not exported. At most **200** notes, in order exam title, task, subtask.
- Front: task context, question text, multiple-choice options as `A.`, `B.`, … and the question crops.
- Back: solution text, the correct option letters, solution crops, and a source line (exam · task · subtask · score).
  Without a stored solution the back says "No solution stored".
- Deck `exam-sim::<Subject>`, tags: Subject and exam title (spaces become `_`).

## Import

Anki: File > Import, pick the `.apkg`. Importing a newer export of the same Subject updates the existing cards instead of
duplicating them (note guids derive from exam and subtask), and your review history is kept.

## Not exported

Unattempted subtasks, hidden exams, solution exams. Review progress in Anki is never read back.
