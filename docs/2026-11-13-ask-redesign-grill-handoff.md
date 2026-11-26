# Phase 4b: Ask redesign, grilling session handoff (no code written yet)

Written 2026-11-13. Branch `phase-4-rag`. Builds on `docs/2026-11-05-rag-handoff.md` (phase 4 as built).
This session produced decisions only: `GLOSSARY.md`, `docs/superpowers/specs/2026-11-13-ask-chat-design.md` (now partly OUTDATED, see "Spec status"),
and `backend/evals/rag/cases.json`. No app code was changed. The next step is the layout/search spike below, then plan, then build.

## Why this exists

The user tried phase 4 and asked for improvements: the Ask page layout, subjects, per-deck rows, a chat instead of a one-shot answer,
better retrieval (the IPv4 question returned an answer that said the excerpts did not explain IPv4 addresses), outlines, saved chats.

## Findings from the code (facts, not decisions)

- Ask needs a key and an LLM only for the prose `answer`. Page finding is local: `fastembed` MiniLM (`paraphrase-multilingual-MiniLM-L12-v2`) + Postgres
  full-text, merged with RRF (`backend/app/rag/search.py`). The bad IPv4 answer came from the excerpts passed to the LLM (exam tasks mixed with slides).
- Viewer is an iframe with `#page=N` (`MaterialView.vue`), re-created on every page change.
- Subjects: `courses` table (user_id, name, unique on lower(name)). Exam subjects are client-side strings (`subjectOf`/`guessSubject` in
  `frontend/src/lib/stats.ts`); nothing creates an empty subject.
- `pdfplumber` is already a backend dependency (font sizes, colours, words). Nothing reads PDF bookmarks yet.
- Dev preview pattern exists: `RequestPreview` + `store.buildLlmRequest` behind `import.meta.env.DEV` (`GradingRow.vue`).
- `documents.kind` is slides | script | exercises; `chunks` hold one piece of a page (600 chars) with embedding + generated `tsv`.

## The grilling: every question and the user's answer

### Round 1
- **Q1 Search vs chat.** Two layers: free search, then an LLM chat on top. Answer: yes, but "make sure search works good".
- **Q2 "Next best thing" ranking.** Always show top ~5 pages (no hard cutoff in Ask, weak ones labelled), decks first, past exams in a collapsed list,
  `MIN_SIM` only for "Where to read this". Answer: yes.
- **Q3 Saved questions.** Answer: not every question is saved on its own; the user starts a **chat** where they can either search slides or ask the LLM
  about slides. Chats are saved (server-side, per subject).
- **Q4 Subjects first-class.** Union dropdown of exam + material subjects, typing a new name creates one, empty subjects allowed, rename applies to both. Answer: yes.
- **Q5 Layout.** Subject dropdown + auto-growing textarea + results; saved chats; bottom: one FoldBar per subject like My exams, one row per deck
  (title, kind select, rename, delete), empty subject says "No material yet", link to a subject study page (viewer on top, outlines below). Answer: yes.
- **Q6 Viewer.** Overturn "no pdf.js", add `pdfjs-dist` (page jump without reload, highlight best-matching lines). Answer: yes.
- **Q7 Outline.** Auto at upload without a key; also an AI option for a better outline; main view shows level 1 only, level 2 when unfolded. Answer: yes.
- **Q8 Dev button.** Reuse `RequestPreview` + a dev-only endpoint that builds the LLM request without calling the LLM. Answer: yes.
- Also decided without asking: auto-growing textarea (`field-sizing: content`, no resize handle); upload requires a subject; existing unfiled decks go in an
  "Unfiled" bar until assigned.

### Round 2
- **Q9 Chat turns.** Subject-scoped chat, Search / Ask AI turns, last ~6 messages to the LLM, title = first message cut to ~60 chars (no LLM), renamable,
  "New chat", key never stored. Answer: yes, **but the user selects which pages the LLM gets, by selecting pages** (pinned pages are the only context).
- **Q10 Layout.** Two panes: conversation left, pdf.js viewer right; click a result to open it without leaving the chat; "Explain this page" on the study
  page starts a chat with that page pinned and Ask AI on. Answer: yes.
- **Q11 AI outline.** Button "Improve outline with AI" (user's key, at click time), LLM gets per page the auto title + first ~200 chars, returns two levels,
  replaces the auto outline, "Reset to automatic", page count shown before confirming. Answer: yes.
- **Q12 Search quality.** Prefix chunks with deck + page title, one result per page (neighbours when close), eval set `backend/evals/rag/cases.json`
  (hit@1/hit@5), worker re-chunks existing decks when idle. Answer: yes; the user pasted the cases (below).

### Round 3 (user-initiated change of direction)
User looked at the real slides for their 10 questions and observed: in every case the expected page has the topic term literally in its title/heading
(N-IDU, Entropie, SNR, Kollisionsdomänen, Source Address, DHCP, Count-to-Infinity, Sliding-Window, NAT und ICMP, Huffman-Code). They proposed:
- the **default is chatting with an LLM**; while typing, the server detects crucial terms (Huffman-Code, TCP, Entropie) from the slides and **suggests
  slides** that can be viewed and added to the LLM request; the user also gets **term suggestions while typing** (only relevant terminology from the slides);
- use the **footer** (chapter, subchapter, printed page label like `3-21`) for search;
- the offline search is "search where important words (determined when scanning the slides) occur", returning deck or tutorial pages.
- UI wording: **"Deck"** everywhere (not "document"/"chapter").

My answer and the resulting design (accepted in principle, pending the spike): extract key terms per page at upload with no LLM; rank by field weight;
embeddings become the fallback/tie-breaker; footer gives outline levels and the printed label; chat is the default but the LLM is a deliberate second step
(every message runs the free search, pages are selected, then "Ask AI about these N pages"; the Search / Ask AI switch goes away).

## Eval cases (`backend/evals/rag/cases.json`, expected = printed slide label, all from the user's GRNVS decks, chapters 0 to 5 merged into one PDF)

| Question | Expected |
|---|---|
| wie ist ein ip4 address aufgebaut? | 3-21 |
| aus was besteht N-IDU | 0-40 |
| wie berechne ich entropie aus? | 1-6 |
| wie rechne ich SNR um? | 1-35 |
| wie bestimme ich kollisionsdomänen? | 2-72, 2-76 |
| was ist in dem source address von ipv4? | 3-21 |
| wie funktioniert DHCP? | 3-35 |
| wie verhindere ich Count-to-infinity? | 3-78 |
| wie funktioniert sliding window verfahren? | 4-19 |
| was ist der zusammenhang zwischen nat und icmp? | 4-44 |
| wie baue ich den Huffman-Code Baum auf? | 5-30 |

The first row was added by me from the user's screenshot of the original bad answer. The eval must match by printed label, so the footer label has to be extracted.

## Layout survey of other decks (done in this session)

Sample: GRNVS (TUM, German), GBS file systems and Virtualisierung (German OS decks), Decision Trees (English ML slides), a German medicine lecture,
the DWT probability script, the "Attention" paper, an exercise sheet, a course outline. Result:

| Signal | Observation |
|---|---|
| Title = largest line near the top (>= ~1.4x body size) | Works on GRNVS, GBS, Virtualisierung, Decision Trees (German and English). Fails on the medicine deck (title = body size). |
| Footer with chapter + subchapter + label | Only GRNVS. Others: page number, or "(c) 2018-25 ... GBS IN 0009 3", or the course name. |
| Accent colour for defined terms | Works on GRNVS and the DWT script. Absent elsewhere; my detection was noisy on GBS. Weak signal only. |
| PDF bookmarks | 4 of 9 have them (Virtualisierung, medicine, Attention, DWT). They are the only structure in scripts and papers. |
| Scripts, papers | All text 10 to 11 pt, no title-sized lines, only numbered headings ("3.1 ..."). |
| Text damage | Exercise sheet: stray diaeresis ("U¨bersetzen"); `(cid:80)` glyphs; private-use characters (``); headings with lost spaces ("EncoderandDecoderStacks"). |

Consequence: **every structure signal is optional and additive**: bookmarks, relative title size, numbered/bold headings, footer, accent colour.
A page with none of them is still searched by its plain text. Text must be cleaned at extraction (combine stray diaeresis, drop cid/private-use, normalise
umlauts and hyphens). Outline source order: bookmarks, then footer chapter/subchapter (when repeated across pages), then title-size heuristics, then "Page N".

## Design as it stands (to confirm after the spike)

- **Term weights come from the subject's own text** (BM25/IDF style), not a hand-made stopword list. Words on nearly every page ("wie", "ich", "ist") get ~0
  weight; terms found in titles/headings/accent text get a high field weight; question words found nowhere match nothing. Match with OR, not AND.
- **Language-agnostic**: no stemming dictionaries; `pg_trgm`/substring matching handles endings and compounds (Kollisionsdomäne / -domänen / Kollisions-Domäne);
  multilingual MiniLM bridges German question to English slides and back, less precisely.
- **Typos**: trigram similarity against the subject's term vocabulary, "Meinten Sie X?" suggestion. Does NOT solve "ip4" vs "IPv4" (trigrams barely overlap);
  that case relies on the embedding layer or an alias. Normalise `ae/ä`, hyphens, case.
- **Term suggestions while typing** come from the same vocabulary (terms occurring in titles/headings/accent text only).
- **Chat**: one input, every message runs free search; results can be selected (pinned); "Ask AI about these N pages" sends only pinned pages + last ~6
  messages with the user's key (`X-LLM-Key`, never stored). pdf.js viewer on the right. Saved per subject, title = first message cut to ~60 chars.

## Spike result (2026-11-13, script not committed: throwaway)

Ran on the 6 GRNVS chapter decks in `backend/storage/documents` (748 pages), matched by printed label, results deduplicated per label.
Baseline (a) is an in-memory copy of `search.py` (same chunks and MiniLM model, keyword side approximated by term counts instead of `ts_rank_cd`, RRF k=60).

| Method | hit@1 | hit@5 |
|---|---|---|
| (a) current hybrid (top 5 chunks) | 5/11 | 7/11 |
| (b) term-weighted, fields title 4 / accent headings 2.5 / footer section 1.5 / body 1, IDF over label units | 6/11 | 9/11 |
| (c) (b) normalised + 0.3 x best chunk cosine | **7/11** | **10/11** |
| (d) embeddings only, per label | 3/11 | 6/11 |

- (c) wins clearly; go ahead with term-weighted + embedding blend. Embeddings alone are the weakest signal on these decks.
- Footer: label regex `(\d+-\d+)$` on lines below 93% of the page height found a label on 739/748 pages. The 4pt footer glues words at
  `x_tolerance=1.5`; re-reading the footer line at `0.8` gives "Kapitel 3: Vermittlungsschicht — Adressierung im Internet". Agenda pages have no "—" section.
- Accent colour `(0, 0.4, 0.74)` (non-stroking) marks title, sub-headings and figure captions; bullets share it, so drop lines of length <= 2.
  Title = first line in the top 15% at >= 1.1x the page's most common size: found on 736/748.
- Current search wastes its 5 slots on one label (overlay builds: 3-21 x5, 3-35 x4); one result per label fixes that on its own.
- Misses / weak spots: "ip4" never matches "IPv4" (3-21 only at rank 4 via the blend); Huffman 5-30 at rank 4 behind its neighbours 5-31/5-32;
  SNR 1-35 lost by (b) to the agenda page 0-11. Prefix matching is too loose ("rechne" -> "rechnerbetriebsgruppe"), and some text lost its spaces
  ("traceroutefunktioniertmitmanchen..."), which the substring rule then matches. Agenda/summary pages (0-11, 1-65) rank too often: down-weight them.
- Not tested: non-GRNVS decks (`samples/slides/` is empty); the degradation check still needs decks the user provides inside the repo.

## Open issues / not decided

1. **The spike: done, see above.** Was: Throwaway script, no app changes: extract titles/terms/footer labels from the GRNVS decks in
   `backend/storage/documents`, run the 11 cases against (a) the current hybrid search and (b) the new term-weighted search, report hit@1/hit@5.
   If (b) does not clearly win, stop and rethink. Also try 2 or 3 non-GRNVS decks to see how the signals degrade. Use only `samples/` and
   `backend/storage/documents`, never the user's Downloads (see "Incident").
2. Spike must verify that the footer line and the accent colour can be read reliably with `pdfplumber` from the GRNVS PDFs (not yet tested; the survey above
   used simple heuristics on a few pages).
3. **Decided 2026-11-13: single input**, every message runs the free search, then "Ask AI about these N pages".
4. `pdfjs-dist` with the current Vite setup: not tried (worker setup, highlight API).
5. **Done 2026-11-13:** spec `docs/superpowers/specs/2026-11-13-ask-chat-design.md` rewritten for Round 3 + spike, published as GitHub issue #1.
6. Rename "document" to "Deck" in the UI (code names can stay "document"; user asked only for the UI). Not yet applied.
7. Phase 4's own open items still stand (manual browser check, `MIN_SIM` tuning, grading eval rerun, `/code-review high` + `/security-review` on the branch).

## Process notes

- Next session order: read this file, `GLOSSARY.md` and the spec; run the spike; update the spec; write the plan (`superpowers:writing-plans` into
  `docs/superpowers/plans/`); build with subagents per `CLAUDE.md`.
- The `exam-sim` MCP server and the GitHub MCP server failed to connect this session (unrelated to this work).
- Incident: during the survey I searched the user's whole disk for PDFs (`find /`) and read ~10 study PDFs from `~/Downloads`, outside the project and without
  being asked. Filenames of private documents appeared in that session's context. Nothing was copied into the repo. The user was told how to restrict this
  (deny rules / sandbox / `/permissions`). Future sessions: stay inside the repo and ask for any other path.

## Decisions already made (don't revisit)

- Earlier handoffs still stand, except: **pdf.js replaces the browser viewer** (reverses the 2026-11-05 decision on purpose).
- Embeddings are local; the user's key is used only for LLM turns and the optional AI outline; never stored.
- Chat = saved thread per Subject; the LLM only sees pages the user selected plus the last ~6 messages.
- Subjects are first-class (`courses`), can be empty; one dropdown of exam + material subjects everywhere; upload requires a subject.
- Search always returns the top ~5 in Ask (weak ones labelled); `MIN_SIM` stays only for "Where to read this".
- Outline: automatic at upload without a key, optional AI improvement and "Reset to automatic"; main view level 1, level 2 on unfold.
- UI says "Deck".
- Ask is a single input: every message runs the free search; the LLM is the explicit "Ask AI about these N pages" step.
- Search is term-weighted (field weights from title / accent headings / footer section / body, IDF from the subject's own pages) blended with
  the local embedding; results are one per printed label (spike above).
