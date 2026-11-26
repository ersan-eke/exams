# Exam Simulator — Frontend Core Loop (Design)

Date: 2026-10-18
Scope: project 1 of 4 (core loop). Later projects: (2) My exams + Statistics, (3) Practice, (4) Quizzes + Ask (LLM).

## 1. Intent

The moment this serves: **one or two days before an exam.** The student has studied and wants a real dress rehearsal with an old exam. Old exams are rare and each one can only be taken fresh once, so that first run must feel like the exam hall: only the paper, a pen, and the clock. Focused, realistic, no distractions.

What makes it different from AI-generated practice sites: the questions are the **real exam**, shown as crops of the original pages (produced by `backend/app/pipeline`), not re-typed or generated.

### Goals
- A serious, realistic simulation of one uploaded exam, one subtask at a time (or several, by choice), against a running clock.
- Answer by typing, drawing, or on the student's own paper.
- After hand-in: honest time statistics (within limit vs. overtime) and grading (self-grading against the solution; MC graded automatically).
- A calm, white, minimal look — Scandinavian/Japanese: lots of white space, thin lines, quiet typography, almost no color.

### Non-goals (this project)
- My exams page, Statistics page, Practice, Quizzes, Ask: present in the menu, show "coming soon".
- LLM grading: the button exists, shows "coming soon".
- Accounts/login: the account icon exists, shows "coming soon". All data is local.
- Scanned-PDF support (pipeline can't do OCR yet; the upload reports a clear error).

### Anti-goals (failure even if it works)
- Anything during the exam that pulls attention away from the exam: hints, solutions, chat, notifications, decorative UI, color.
- Seeing any solution before hand-in.
- Losing answers on reload or a closed laptop.
- Re-rendering the exam as text instead of showing the original crops.

## 2. Constraints

- Frontend: Vue 3 + TypeScript + Pinia + Vue Router, already scaffolded in `frontend/` (Vite). PrimeVue 4 is installed but unused.
- Backend: FastAPI in `backend/`; the pipeline lives in `backend/app/pipeline` and produces `exam.json` (see `models.py`: `ExamStructure → Task → Context / Subtask → Region(page, bbox, image)`) plus PNG crops.
- **Exams are stored only in the browser** (IndexedDB), never on the server. The server processes an upload and keeps nothing.
- Must work on a laptop and on a tablet (drawing with a pen). Phone should not break (outline becomes an overlay).

## 3. The app frame (all pages except the running exam)

- **Top bar:** product name (placeholder, e.g. "Examen") on the left; on the right a **gear** (app settings) and to its right an **account icon** (coming soon).
- **Left menu, collapsible** (« / ») into a thin rail: New exam · My exams · Statistics — separator — Practice · Quizzes · Ask. Only *New exam* works in this project; the others show a quiet "coming soon" page.
- **App settings (gear)** are app-wide only, e.g. default answer mode, attendance check on/off default, (later) LLM API key.

## 4. Flow

### 4.1 New exam (start page)
- The main area shows one thing: a drop zone / "Choose file" for a PDF ("exam or solution · stays on this device").
- Upload → backend processes it → progress state ("Reading the exam…") → on success the exam is stored in IndexedDB.
- Errors are plain and specific: not a PDF, scanned PDF not supported yet, no tasks found.
- If the pipeline reports warnings (e.g. points don't add up), the exam is still usable; show the note quietly (a reviewing/correction UI is a later phase).

### 4.2 Exam settings (between upload and start)
Short, one screen: exam title (editable), number of tasks/points (read-only summary), **time limit** (prefilled from the exam if known, else 90 min), which tasks to include (all by default), attendance check on/off. Then **Start**.

### 4.3 The simulation (focus mode)
When the exam starts, the app frame disappears: no menu, no gear, no account icon.

**Top bar:** exam name (left) · clock (center, tabular numerals) · **Hand in** (right).

**Left: exam outline** — collapsible into a thin rail.
- Works like a file navigator: tasks (number, title, points) fold/unfold to show their subtasks a), b), c)… with points.
- Context blocks of a task are listed too, so the student can jump to the diagram.
- Status: filled dot = answered; grey bar = currently shown on the sheet.
- **Click a row** = show only that subtask.
- **Hover a row → eye icon**; clicking the eye adds/removes that subtask to/from the sheet. Multiple shown subtasks are always ordered as in the exam.

**Middle: the sheet** — one narrow column (≈ paper width), centered, lots of white.
- The task's context (stem, and any intermediate context whose `applies_from` is at or before the shown subtask) sits under its own **fold bar** ("Context · Aufgabe 2"), open by default the first time, folded state remembered.
- Every displayed subtask also sits under its own **fold bar** ("Aufgabe 2 · b) · 1 P") so e.g. b) can be folded while c) stays open.
- Each subtask shows its crop(s) (a subtask may span pages → several crops, stacked), then its **answer area** with a quiet switch: **Type · Draw · On paper**.
  - *Type:* a plain multi-line text field.
  - *Draw:* a canvas below the crop with pen / eraser / clear; works with pen, touch, mouse, trackpad.
  - *On paper:* no input; a "done" toggle so the subtask counts as answered.
  - **Multiple choice:** checkboxes are clickable **directly on the crop**, positioned from the pipeline's box coordinates (prototype validated on GRNVS 2019 6e). Clicking the option text may also tick it. If no box positions exist, fallback: a list of buttons under the crop in the same order/layout.
- **Bottom:** previous / next subtask.

**Attendance check:** at one random moment within the first 30 minutes, a modal "Attendance check — a tutor is checking your ID" appears for 5 seconds; it can't be dismissed, the clock keeps running, then the exam resumes. Can be turned off in exam settings.

**Time is up:** a modal says the exam time is over and it's time to hand in. Choices: **Hand in** (ends the simulation) or **Keep going** (overtime). In overtime the clock counts up in a different, muted warm tone (e.g. "+04:12"). Overtime is recorded separately everywhere.

**Persistence:** answers, drawings, MC ticks, outline state, and timing are saved continuously to IndexedDB. Reloading or reopening resumes the running exam (the clock is based on wall-clock start time, so time passes while the tab is closed — like a real exam).

**Hand in** (button or timer modal) asks for a short confirmation, then ends the attempt.

### 4.4 After hand-in (results)
First, time — simple, minimal:
- time used within the limit · overtime · subtasks answered within the limit;
- a toggle "Time per subtask" reveals a bar list sorted by time spent (biggest time sinks first).
  Time counts for a subtask while it is open on the sheet; when several are open the time is split evenly between them.

Then grading, three buttons:
- **Compare with solution** — available if the uploaded PDF was a solution PDF, or after the student uploads the solution PDF now. Shows, per subtask, the student's answer next to the solution crop (from the solution PDF, solution ink visible) and a points picker (0 to max in 0.5 steps). MC is graded automatically and shown as such.
- **Grade myself** — same points pickers without a solution.
- **Ask an LLM to grade** — coming soon.

**Scores (user decision).** When the time limit is reached, the app freezes a snapshot of every answer (text, strokes, MC ticks, "done" toggles).
- **Main score** = the grade of the snapshot: what the student achieved in normal time. Shown first and most prominently.
- **Overtime score** = the grade of the final answers. Shown second, quieter.
- Grading: a subtask untouched in overtime is graded once and counts for both scores. A subtask changed or first answered in overtime gets two points pickers (snapshot version, final version).
- If the student handed in before the limit, there is only the main score.

**Multiple-choice scoring (user decision).** The pipeline reads the grading rule from the exam's instructions (they almost always state it, e.g. GRNVS: +1 per correct tick, −1 per wrong tick, minimum 0 per subtask). If no rule is found, the default is **all-or-nothing**. The rule is shown (and changeable) on the exam settings screen. The student can override the automatic grade of a single subtask.

Results are stored with the attempt in IndexedDB (used later by Statistics/Practice).

### 4.5 Returning to exams before "My exams" exists (user decision)
- Only one exam can be running at a time. Opening the site while one is running offers **Continue exam**.
- The start page shows a quiet list of the last few exams under the drop zone, to reopen results or upload the solution later.
- Retaking an exam is allowed but the attempt is marked **not fresh**, so statistics stay honest.

## 5. Visual language
- White background, near-black ink (`#1c1c1c`), muted grey for secondary text (`#8a8a85`), hairline lines (`#e8e7e3`), a faint warm off-white for answer areas (`#fbfbf9`). No accent color except the muted warm tone for overtime.
- One sans-serif family (e.g. Inter, system fallback), small uppercase letter-spaced labels, tabular numerals for times/points.
- Thin borders, no shadows, no rounded "card" look, generous spacing. Icons line-style and few.
- The mockups in `.superpowers/brainstorm/*/content/` (exam-layout-v3, home-v1, results-v1, mc-overlay) are the reference.

## 6. Backend / pipeline work this needs

**Order and definition of done (user decision).** The frontend is built first and must fully work with what the pipeline already delivers: MC falls back to the button list, grading is self-grading. The pipeline additions below are a second track, each plugging in when ready. Done = GRNVS, GBS and IT-Sec exams (TUM template) work end to end, including MC ticked directly on the crop.

- **Upload endpoint:** `POST` a PDF → run the pipeline in a temp dir → return the exam structure plus the crops (e.g. JSON with base64 images, or JSON + a zip) → delete everything. Synchronous handler as a plain `def` is fine for now (a few seconds per exam).
- **Exam duration:** extract it from the cover page when stated ("Arbeitszeit 150 Minuten", "Uhrzeit 11:00–12:30") so the settings screen can prefill it.
- **MC detection:** for each subtask, detect answer options (checkbox rects or box/circle glyphs) with their positions relative to the crop, and the option text; in solution PDFs, which boxes are ticked → answer key. Mark the subtask as MC. Also read the MC grading rule from the exam's instructions (§4.4).
- **Solution matching:** when a solution PDF is uploaded after an exam, match its subtasks to the exam by task/subtask id (same template), returning solution crops (rendered *with* solution ink) and solution text.

## 7. Decided by the builder (Claude's calls, not yet confirmed by the user)
- PrimeVue is not used for the look; components are hand-written with CSS variables so the minimal style isn't fighting a theme. PrimeVue may be used unstyled for behavior-heavy pieces (dialogs, focus trapping) if it helps.
- The drawing canvas stores strokes as vector data (not bitmaps).
- Default answer mode is *Type*, changeable per subtask and as an app setting.
- Points picker step is 0.5.
- The clock is wall-clock based (time passes while the tab is closed).
- Account icon and non-core menu pages show a simple "coming soon".
- The student can override an automatic MC grade per subtask.
- Time per subtask: counted while the subtask is open (unfolded) on the sheet and the tab is visible; split evenly between open subtasks.
- A subtask without known points gets a free-number points field instead of a picker.
- Solution PDFs are rendered twice: without solution ink for the exam, with it for "Compare with solution".

## 8. Left to the builder
Component structure, store shape, IndexedDB library, routing, how crops are transferred from the backend, test strategy, exact spacing/type scale (following §5 and the mockups).
