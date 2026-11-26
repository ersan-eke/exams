# Phase 4b: Ask as a Chat over a Subject's Decks, term-weighted Search, Outlines

Vocabulary: `GLOSSARY.md` (Subject, Material, Deck, Outline, Search, Chat, Pinned page, AI turn).
Sources: grilling rounds 1 to 3 and the search spike in `docs/2026-11-13-ask-redesign-grill-handoff.md`. Replaces the round-2 version of this spec. Tracked as GitHub issue #1 (`ready-for-agent`).

## Problem Statement

Phase 4 gives a student one question box per Subject that sends the question plus five retrieved excerpts to an LLM and shows one prose answer.
In practice that fails the student in several ways:

- The answer is often wrong or evasive because the excerpts are wrong. Asking how an IPv4 address is built returned an answer saying the material
  did not explain IPv4 addresses, although slide 3-21 is exactly that. On the student's own 11 test questions, the current search puts the right
  slide first only 5 times and in the top 5 only 7 times. Its top 5 is often the same slide five times (overlay builds of one slide).
- Every question costs an LLM call and needs a key, even when the student only wants to know where something is in the slides.
- The student cannot steer what the LLM sees, cannot follow up, and loses every answer when they leave the page.
- The page layout is cramped: Subjects exist only implicitly, a Subject cannot be created before it has content, Decks cannot be managed per
  Subject, there is no overview of what a Deck contains, and the viewer reloads the whole PDF on every page change.

## Solution

Ask becomes a saved Chat per Subject with one input. Every message first runs a free, local Search over the Subject's Decks (no key, no LLM)
that returns the best five slides, one per printed slide label, and opens the best one in a pdf.js viewer next to the conversation.
While typing, the student gets term completions from the Subject's own slide vocabulary and a live preview of matching slides.
The student pins the slides that matter and, only when they want an explanation, presses "Ask AI about these N pages": the LLM, with the
student's own key, sees only the pinned pages plus the last few messages. Chats are saved and listed per Subject.

Search ranks by the words that matter in this Subject: terms found in slide titles, accent-coloured headings and the footer section weigh most;
words found on nearly every page ("wie", "ist") weigh nothing; the local embedding breaks ties and catches paraphrases. In the spike this
raised the student's eval from 5/11 to 7/11 at rank 1 and from 7/11 to 10/11 in the top 5.

Subjects become first-class: they can be created empty, renamed once for exams and Material alike, and every Deck upload needs one.
Each Deck gets an automatic Outline at upload (no key) that the student can improve with AI and reset. A study page per Subject shows the
viewer with the Decks' Outlines below it.

## User Stories

Subjects
1. As a student, I want to create a Subject before I have uploaded anything, so that I can set up my semester first.
2. As a student, I want one Subject dropdown that lists both my exam Subjects and my Material Subjects, so that I never see two lists that disagree.
3. As a student, I want to type a new name into the Subject dropdown to create it, so that creating a Subject takes no extra dialog.
4. As a student, I want to rename a Subject once and have exams and Decks follow, so that names stay consistent.
5. As a student, I want Subject names to be case-insensitive unique, so that "GRNVS" and "grnvs" are not two Subjects.
6. As a student, I want an empty Subject to say "No material yet", so that I know it exists and what is missing.
7. As a student, I want Decks I uploaded before Subjects were required to show in an "Unfiled" group until I assign them, so that nothing gets lost.

Decks
8. As a student, I want every Deck upload to ask for a Subject, so that Search always knows where a Deck belongs.
9. As a student, I want one collapsible bar per Subject with one row per Deck, like My exams, so that the Ask page stays tidy.
10. As a student, I want to change a Deck's kind (slides, script, exercises) from its row, so that a wrong guess is easy to fix.
11. As a student, I want to rename and delete a Deck from its row, so that I can manage Material in one place.
12. As a student, I want the UI to say "Deck" everywhere, so that the wording matches how I think about slides.
13. As a student, I want Decks I already uploaded to become searchable the new way without re-uploading, so that the upgrade costs me nothing.

Search
14. As a student, I want every message I send to search my Subject's Decks for free, so that finding a slide never needs a key.
15. As a student, I want the five best slides for my question, so that I can choose instead of trusting one answer.
16. As a student, I want each result to be a different slide, so that overlay builds of one slide do not fill the list.
17. As a student, I want each result to show the Deck, the printed slide label (like 3-21) and the slide title, so that I recognise it.
18. As a student, I want weak results labelled as weak rather than hidden, so that I still see the closest thing when nothing fits well.
19. As a student, I want slides to come before past exam tasks, with exam tasks in a collapsed list, so that study material comes first.
20. As a student, I want filler words in my question ignored, so that "wie berechne ich entropie" finds the Entropie slide.
21. As a student, I want word endings and compounds handled (Kollisionsdomänen / Kollisionsdomäne / Kollisions-Domäne), so that I need not guess the exact form.
22. As a student, I want umlauts, "ae"-style spellings, hyphens and case to be ignored, so that how I type does not matter.
23. As a student, I want a German question to still find English slides and the other way round, so that mixed-language courses work.
24. As a student, I want a "Did you mean X?" suggestion when I mistype a term that exists in my slides, so that typos do not sink a search.
25. As a student, I want agenda and summary slides not to crowd out the slide that explains the topic, so that the top result is the real one.
26. As a student, I want Search to stay inside my selected Subject and my account, so that results are never someone else's or another course's.
27. As a student, I want Search to work on slides without footers, colours or bookmarks too, so that every Deck is searchable by its plain text.
28. As a student, I want damaged PDF text (stray diaeresis, unreadable glyphs, private-use characters) cleaned up, so that those pages still match.

Typing help
29. As a student, I want term completions while typing that come only from my Subject's slide titles and headings, so that suggestions are relevant terminology.
30. As a student, I want a live preview of matching slides while I type, so that I can see whether my wording works before I send it.

Chat
31. As a student, I want Ask to be a Chat with one input, so that I can follow up instead of starting over.
32. As a student, I want my Chats saved per Subject on the server, so that they are there on my other devices and after reloads.
33. As a student, I want a new Chat to be titled after my first message (cut to about 60 characters), so that the list is readable without an LLM.
34. As a student, I want to rename a Chat, so that I can find it later.
35. As a student, I want a "New chat" button and the list of my Chats for the selected Subject, so that I can switch topics.
36. As a student, I want to delete a Chat, so that the list stays useful.
37. As a student, I want to pin result slides in a Chat, so that I decide what the LLM gets to read.
38. As a student, I want to unpin a slide, so that I can correct my selection.
39. As a student, I want to see how many slides are pinned on the "Ask AI about these N pages" button, so that I know what I am sending.
40. As a student, I want the LLM to see only my pinned slides and the last few messages, so that the answer is about the slides I chose and the request stays small.
41. As a student, I want the AI answer to cite the pinned slides it used, so that I can check it.
42. As a student, I want the AI step to use my own key from my settings and never store it on the server, so that my key stays mine.
43. As a student, I want a clear message when I have no key, a bad key, no credits or hit a rate limit, so that I know what to fix.
44. As a student, I want Search turns to keep working without a key, so that the free part never depends on the paid part.

Viewer
45. As a student, I want a PDF viewer to the right of the conversation, so that I read slides without leaving the Chat.
46. As a student, I want clicking a result to jump the viewer to that slide without reloading the PDF, so that browsing results is fast.
47. As a student, I want the words that matched highlighted on the slide, so that I see why it was found.

Outline and study page
48. As a student, I want each Deck to get an Outline automatically at upload without a key, so that I can see what it contains immediately.
49. As a student, I want the Outline built from the best structure the Deck has (bookmarks, footer chapters, title sizes, else "Page N"), so that it works on slides, scripts and papers.
50. As a student, I want the Outline to show level 1 first and level 2 when I unfold a section, so that a long Deck stays scannable.
51. As a student, I want a study page per Subject with the viewer on top and the Decks' Outlines below, so that I can read a whole chapter.
52. As a student, I want clicking an Outline entry to jump the viewer to that page, so that the Outline is navigation.
53. As a student, I want an "Improve outline with AI" button that tells me how many pages it will send before I confirm, so that I control the cost.
54. As a student, I want "Reset to automatic" after an AI Outline, so that a bad AI result is not permanent.
55. As a student, I want "Explain this page" on the study page to start a Chat with that page pinned, so that I go from reading to asking in one click.

Where to read this
56. As a student, I want "Where to read this" under an exam task to keep showing only confident slide links, so that it never points at unrelated slides.

Developer
57. As the developer, I want a dev-only button that shows the exact LLM request for an AI turn without sending it, so that I can debug prompts at no cost.
58. As the developer, I want a local eval that reports hit@1 and hit@5 by printed label on real Decks, so that search changes are measured, not guessed.

## Implementation Decisions

Subjects
- The existing per-user `courses` table is the Subject. A Subject list endpoint returns every Subject of the user, including empty ones and
  the ones only exams use; create and rename endpoints keep the case-insensitive unique name. Exams that carry only a client-side Subject
  string get their course row on first use (as today).
- Deck upload requires a Subject; Decks with no Subject are listed as "Unfiled" and can be assigned with the existing Deck update.

Page structure (new, extracted at upload by the worker, no key)
- Each Deck page yields: printed label, footer chapter and section, page title, accent headings, cleaned body text. Every signal is optional and
  additive; a page with none of them is still searched by its body text.
- Printed label: a trailing `N-M` (or page number) on a line in the bottom ~7% of the page. The footer line is re-read with a tighter word gap
  because small footer text glues words together; chapter and section are split on the dash.
- Title: PDF bookmark for that page when the Deck has bookmarks; otherwise the first line in the top ~15% of the page at >= 1.1x the page's most
  common text size.
- Accent headings: lines whose dominant text colour is the Deck's accent colour (the most frequent non-black colour of title-sized lines),
  excluding bullet glyphs and lines of two characters or fewer. Absent on many Decks; treated as a weak bonus only.
- Text cleanup at extraction: combine stray diaeresis, drop `(cid:N)` and private-use characters, normalise hyphens; normalisation for matching
  folds case and umlauts (ä/ae) and also indexes hyphenated compounds joined (count-to-infinity also as counttoinfinity).
- Storage: a new per-page table keyed by Deck and page, with the label, title and section as columns (filtered and grouped on), and the
  per-field term counts and headings as JSONB (read whole). The existing chunks stay for embeddings, now prefixed with Deck title and page title.
- Existing Decks without page rows are re-extracted and re-chunked by the worker while idle, the same way exam subtasks are indexed today.

Search (replaces the scoring in the current hybrid search; same per-user, per-Subject scoping)
- Unit of result: one printed label of one Deck (overlay builds share a label); pages without a label are their own unit.
- Term score: BM25-style. IDF is computed over the Subject's own units, so filler words get ~0 weight without any stopword list. Field weights
  from the spike: title 4, accent headings 2.5, footer section 1.5, body 1. Saturating term frequency. Query terms are OR-ed.
- Term matching against the Subject vocabulary: exact match full weight; prefix and inflection matches reduced and limited to a few extra
  characters (the spike showed unlimited prefixes match "rechne" to "rechnerbetriebsgruppe"); substring (compound) matches only for query terms
  of five or more characters and only against title/heading terms, so glued text no longer matches everything.
- Agenda and summary pages (title equals the Deck's chapter title, or the page lists many section headings) are down-weighted.
- Final score: normalised term score + 0.3 x the unit's best chunk cosine (local MiniLM, unchanged model). Embeddings alone were the weakest
  method in the spike, so they only blend and break ties.
- Always the top 5 units; units with no term match and a cosine below `MIN_SIM` are marked weak. Past exam subtasks are ranked by the existing
  embedding + full-text path and returned as a separate list.
- Typos: trigram similarity of unmatched query terms against the Subject vocabulary gives a "Did you mean" term. The "ip4" vs "IPv4" case is not
  solved by trigrams and is left to the embedding blend.
- Term completion: prefix matches over the Subject vocabulary restricted to terms that occur in titles, headings or footer sections, ranked by
  how many units carry them.
- "Where to read this" keeps its `MIN_SIM` filter and gains the one-result-per-label rule.

Chat
- New `chats` table: id, user, Subject, title, created and updated time as columns; messages and pinned pages as JSONB (read and written whole).
- Message kinds: user message; search turn (the result refs: Deck, page, label, title, weak flag, matched terms); AI turn (answer, cited pinned
  pages, provider and model). Never the key.
- Endpoints: list Chats of a Subject, create, rename, delete, get one; post a message (stores it, runs Search, stores the search turn, returns
  both); set pinned pages; AI turn (requires `X-LLM-Key`, uses the existing ask rate limiter and `complete` with the student's provider and
  model, sends only the pinned pages' text plus the last ~6 messages, appends the answer). A preview search endpoint for the typing preview runs
  the same Search without saving. The one-shot ask endpoint is removed.
- Title = first message cut to ~60 characters.
- Dev-only endpoint returns the AI turn request as built, without calling the LLM; the frontend shows it with the existing request preview
  component behind the dev-build check.

Outline
- Stored on the Deck as JSONB (two levels: entries with title and page, level-2 entries under each level-1 entry) plus its source (automatic or AI).
- Automatic source order: PDF bookmarks; else footer chapter/section when repeated across pages (section = level 1, page titles = level 2);
  else title-size headings with equal consecutive titles merged; else "Page N".
- AI outline endpoint (student's key at click time): sends per page the automatic title plus the first ~200 characters, receives two levels,
  replaces the Outline; a reset endpoint rebuilds the automatic one. The UI shows the page count before confirming.

Frontend
- Ask page: Subject dropdown (union, create by typing), Chat list with New chat and rename, conversation on the left, viewer on the right,
  auto-growing input, term completions and debounced live preview while typing, result rows with pin toggles, "Ask AI about these N pages".
  Bottom: one fold bar per Subject with Deck rows (title, kind select, rename, delete), "No material yet", "Unfiled", link to the study page.
- Study page per Subject: viewer on top, Decks below with level-1 Outline, level 2 on unfold, "Improve outline with AI", "Reset to automatic",
  "Explain this page".
- Viewer: a `pdfjs-dist` component (replaces the iframe; reverses the 2026-11-05 decision on purpose) that keeps the document loaded, jumps
  pages without reload and highlights matched terms in the text layer. Its worker setup under Vite is the first thing to verify.
- UI text says "Deck"; code names may stay "document".

## Testing Decisions

- Good tests drive the system from outside and assert what a student or a client sees: HTTP responses, stored Chats, rendered views. They do not
  assert scoring internals, weights or SQL.
- Backend seam: the HTTP API with `TestClient` against `examsim_test`, uploads processed by the worker's `run_once`, `embed` faked, the LLM adapter
  mocked. Prior art: the RAG ask tests and the Deck upload tests. Covers Subjects (create empty, union, rename, case-insensitive uniqueness,
  upload requires a Subject, Unfiled); upload producing page labels, titles, headings and an automatic Outline; Search (right slide first on a
  synthetic Deck, one result per label, top 5 with weak flag, filler words ignored, inflected and hyphenated forms, cross-Subject and
  cross-account isolation, works with no structure signals); term completion and "Did you mean"; Chats (create, title, rename, list per Subject,
  delete, foreign Chat 404); AI turns (only pinned pages and the last ~6 messages reach the mocked LLM, key required, key never stored in the
  Chat or logged, error codes); AI outline and reset; the dev request preview; existing Decks re-extracted by the idle worker.
- The synthetic PDF test helper gains per-line font size, colour and position, so tests can build Decks with a title, accent headings and a
  footer label. No new production seam.
- Search-quality eval: the existing RAG eval cases (questions with expected printed labels), run locally on real Decks through the same upload
  and Search code, reporting hit@1 and hit@5. Not in CI (copyrighted Decks). Gate: at least the spike's 7/11 and 10/11.
- Frontend seam: view specs with mocked stores and fetch, as in the existing Ask and Material view specs. The pdf.js viewer is mocked at its
  component boundary (no worker or canvas in jsdom). Covers Subject dropdown and creation, Chat list and switching, send message shows results,
  pinning updates the Ask AI button count, Ask AI disabled without a key, readable errors, Deck rows, Outline folding, "Explain this page".

## Out of Scope

- Streaming AI answers, OCR of scanned Decks, hand-editing Outlines, pairing exercise sheets with their solutions.
- Searching across Subjects; sharing Chats; storing or proxying the student's key.
- Stemming dictionaries, hand-made stopword lists, LLM-built term lists, aliases like "ip4" -> "IPv4".
- Changing the embedding model.
- Tuning on non-GRNVS Decks: the spike could not test them (`samples/slides/` is empty); the eval is extended when the student adds some.

## Further Notes

- Spike (2026-11-13, 6 GRNVS Decks, 748 pages): current hybrid 5/11 hit@1, 7/11 hit@5; terms only 6/11, 9/11; terms + 0.3 cosine 7/11, 10/11;
  embeddings only 3/11, 6/11. Labels found on 739/748 pages, titles on 736/748. Remaining misses: "ip4" (rank 4), Huffman 5-30 behind its
  neighbours 5-31/5-32, SNR lost to the agenda slide 0-11 without the blend.
- Phase 4 open items still apply: manual browser check, `MIN_SIM` tuning, grading eval rerun, `/code-review high` and `/security-review` on the branch
  (keys and new endpoints are touched).
- Decisions in the handoff's "Decisions already made" are settled.
