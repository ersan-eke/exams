# Graph Report - exam-sim  (2026-11-27)

## Corpus Check
- 289 files · ~226,553 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 18 file(s) not represented in the graph (top: (none) 10, .example 2, .ini 1)

## Summary
- 3735 nodes · 10405 edges · 161 communities (141 shown, 20 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 902 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `5177152f`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- stores/attempt.ts
- test_mcp_tools.py
- db.ts
- sqlalchemy
- chats.py
- api/sync.py
- Chat Pane
- ResultsView.vue
- extract.py
- signed_in
- routes.py
- Pipeline Task Model and MC
- documents.py
- PDF Layout Grouper
- test_api.py
- test_mcp_tools.py
- GradingList.vue
- test_sync.py
- signed_in
- Frontend CI Workflow
- ResultsView.vue
- Grading Errors and Streaming
- Phase 5b-1 handoff: Anki export
- settings
- test_rag_slides.py
- Text Enrichment
- grading.ts
- MC Detection
- test_notion_client.py
- exam.ts
- test_chats.py
- build_card
- useAttemptStore
- make_pdf
- deck.py
- hints.py
- test_slack_events.py
- test_anki.py
- Documents Client API
- notion/client.py
- test_grading.py
- Sub/Superscript Folding
- Job
- structure.py
- MCP Tokens UI
- outline.py
- Course
- test_eval_scans.py
- json
- test_visual.py
- StudyView.vue
- Task 5: The exporter
- FakeStream
- test_grading_api.py
- NotionIntegration.vue
- choice
- test_integrations.py
- watch
- test_rag_outline.py
- devDependencies
- test_slack_crops.py
- api/sync.py
- db
- grader.py
- ExamSettingsView.vue
- scoring.ts (mcPoints, scores, changedInOvertime)
- test_notion_export.py
- ChatPane.spec.ts
- deck.py
- server.py
- test_slack_quiz.py
- conftest.py
- AddMaterial.vue
- index.py
- ExamModals.vue
- package.json
- PdfViewer.vue
- test_api.py
- uuid
- Term-weighted search blended with embeddings
- current_user dependency (401)
- scripts
- eslint.config.ts
- process
- Slack /quiz: page crops, kept question, self-check (design)
- exam-sim project
- grader.py (grade_stream, finalize, GradingError)
- Plan: Phase 3a Auth + Sync
- dependencies
- api/auth.py
- tsconfig.app.json
- tsconfig.vitest.json
- StatisticsView.vue
- environment
- Hybrid search (tsvector + pgvector RRF)
- vite.config.ts
- vue
- fixture
- interactions
- api/ask.py
- LLM grading core (solution-first)
- RAG Ask (phase 4)
- Two-way sync (exams and attempts)
- Plan: Frontend Core Loop
- Spec: Phase 2b Text-first grading inputs
- X-LLM-Key header (never stored or logged)
- .oxlintrc.json
- NotionDatabase
- PdfDropZone.vue
- Phase 5b: flashcard export, Anki first, then Notion (design)
- FakeClient
- Exam-sim upgrade roadmap
- MCP server at /mcp
- Client grading library (planGrading, streamGrade)
- mcp/auth.py
- Fake
- Text-first grading inputs
- .prettierrc.json
- select
- docling enrichment (enrich.py)
- tsconfig.json
- pipeline-smoke.sh
- Iframe browser PDF viewer with #page=N
- frontend README (Vue 3 Vite template)
- db/models.py
- Testing levels (pipeline smoke test)
- exam-sim-backend
- export.py
- Review Focus
- step
- FakeGStream
- conftest.py
- resolve_model
- test_subjects.py
- ExamModals.vue
- ExportFailed
- SubjectSelect.vue
- clock
- PdfDropZone.vue
- services
- embed.py
- test_slack_events.py
- invite_only_uploads
- db
- x-backend-env
- Modal.vue
- _Token
- MaterialView.spec.ts
- signed_in_user
- api
- migrate
- worker
- Quiz yourself from Slack
- Flashcards in Notion
- cloudflared
- x-backend

## God Nodes (most connected - your core abstractions)
1. `User` - 95 edges
2. `signed_in()` - 91 edges
3. `select()` - 89 edges
4. `Exam` - 61 edges
5. `useAttemptStore` - 55 edges
6. `Job` - 54 edges
7. `vue` - 54 edges
8. `vitest` - 53 edges
9. `Course` - 46 edges
10. `course_id()` - 43 edges

## Surprising Connections (you probably didn't know these)
- `Constraints` --references--> `_scored()`  [INFERRED]
  docs/superpowers/specs/2026-11-23-phase-5b-anki-notion-design.md → backend/app/mcp/tools.py
- `Anti-goals` --references--> `_crops()`  [INFERRED]
  docs/superpowers/specs/2026-11-23-phase-5b-anki-notion-design.md → backend/app/mcp/tools.py
- `Decisions already made` --references--> `get_task()`  [INFERRED]
  docs/2026-11-23-phase-5b1-handoff.md → backend/app/mcp/tools.py
- `Known limits` --references--> `answer()`  [INFERRED]
  docs/2026-11-24-slack-crops-handoff.md → backend/app/slack/quiz.py
- `Task 6: Settings card in the frontend` --references--> `disconnectIntegration()`  [INFERRED]
  docs/superpowers/plans/2026-11-20-phase-5a-slack.md → frontend/src/lib/integrations.ts

## Import Cycles
- 3-file cycle: `backend/app/grading/grader.py -> backend/app/grading/providers/__init__.py -> backend/app/grading/providers/anthropic.py -> backend/app/grading/grader.py`
- 3-file cycle: `backend/app/grading/grader.py -> backend/app/grading/providers/__init__.py -> backend/app/grading/providers/google.py -> backend/app/grading/grader.py`
- 3-file cycle: `backend/app/grading/grader.py -> backend/app/grading/providers/__init__.py -> backend/app/grading/providers/openrouter.py -> backend/app/grading/grader.py`

## Hyperedges (group relationships)
- **Chat turn flow (search, pin pages, AI turn)** — glossary_chat, glossary_search, glossary_pinned_page, glossary_ai_turn [EXTRACTED 1.00]
- **LLM grading provider adapters** — docs_superpowers_plans_2026_10_29_llm_grading_anthropic_adapter, docs_superpowers_plans_2026_10_29_llm_grading_google_adapter, docs_superpowers_plans_2026_10_29_llm_grading_openrouter_adapter [EXTRACTED 1.00]
- **MCP tools over user data** — docs_superpowers_plans_2026_11_03_mcp_read_tools, docs_superpowers_plans_2026_11_03_mcp_write_tools, docs_superpowers_plans_2026_11_03_mcp_bearer_auth [EXTRACTED 1.00]
- **Two-way sync flow** — docs_superpowers_plans_2026_11_02_sync_put_exam, docs_superpowers_plans_2026_11_02_sync_put_attempt, docs_superpowers_plans_2026_11_02_sync_get_sync, docs_superpowers_plans_2026_11_02_sync_sync_ts [EXTRACTED 1.00]
- **MCP practice session pipeline** — docs_mcp_tools, docs_2026_11_04_mcp_handoff_access_tokens, docs_2026_11_04_mcp_handoff_record_practice, docs_2026_11_03_sync_handoff_two_way_sync [INFERRED 0.85]
- **RAG retrieval stack** — docs_2026_11_05_rag_handoff_local_embeddings, docs_2026_11_05_rag_handoff_documents_chunks, docs_2026_11_05_rag_handoff_hybrid_search, docs_2026_11_13_ask_redesign_grill_handoff_term_weighted_search [INFERRED 0.85]

## Communities (161 total, 20 thin omitted)

### Community 0 - "stores/attempt.ts"
Cohesion: 0.08
Nodes (30): store, model, points, props, shown, SKIPS, skipText, verdict() (+22 more)

### Community 1 - "test_mcp_tools.py"
Cohesion: 0.12
Nodes (31): parse_allowed_emails(), Answer, Grade, find_tasks(), record_practice(), test_allowlist_strips_lowercases_and_skips_empty(), test_allowlist_that_parses_empty_refuses_to_start(), call() (+23 more)

### Community 2 - "db.ts"
Cohesion: 0.08
Nodes (59): props, src, attemptsForExam(), clearDirty(), db(), dirtyIds(), dirtyKey(), emptyView() (+51 more)

### Community 3 - "sqlalchemy"
Cohesion: 0.06
Nodes (16): run_migrations_offline(), run_migrations_online(), upgrade(), upgrade(), upgrade(), upgrade(), upgrade(), upgrade() (+8 more)

### Community 4 - "chats.py"
Cohesion: 0.10
Nodes (27): ask_preview(), ask_turn(), AskTurnIn, ChatIn, create_chat(), delete_chat(), get_chat(), list_chats() (+19 more)

### Community 5 - "api/sync.py"
Cohesion: 0.11
Nodes (21): _put_attempt(), _f(), _ids(), read_attempt(), subtask_keys(), write_attempt(), SubtaskTime, _auto() (+13 more)

### Community 6 - "Chat Pane"
Cohesion: 0.07
Nodes (51): askAi(), asking, busy, chat, chats, error, fresh(), hints (+43 more)

### Community 7 - "ResultsView.vue"
Cohesion: 0.08
Nodes (26): decode(), errorFor(), followJob(), JobEnd, send(), serverCodes, UploadError, UploadErrorCode (+18 more)

### Community 8 - "extract.py"
Cohesion: 0.17
Nodes (13): base_font(), drop_margin_graphics(), key(), margin(), near_edge(), extract_page(), find_grading_boxes(), glyph_checkboxes() (+5 more)

### Community 9 - "signed_in"
Cohesion: 0.14
Nodes (20): stored_uploads(), test_a_lost_insert_race_answers_like_a_duplicate(), test_deck_over_the_cap_is_413(), test_decks_keep_upload_order_and_unfiled_ones_can_be_assigned(), test_delete_removes_chunks_and_file(), test_exam_upload_cleans_nul_from_filename(), test_foreign_documents_are_404(), test_get_one_document_is_owner_only() (+12 more)

### Community 10 - "routes.py"
Cohesion: 0.08
Nodes (16): invited_user(), check_declared(), _encode(), get_exam(), get_job(), grade(), _grade_request(), job_events() (+8 more)

### Community 11 - "Pipeline Task Model and MC"
Cohesion: 0.12
Nodes (42): Subtask, Task, apply_header_points(), derive_mc(), fill_remainder(), _half_step(), header_points(), HeaderPoints (+34 more)

### Community 12 - "documents.py"
Cohesion: 0.09
Nodes (23): _by_sha(), delete_document(), document_file(), DocumentOut, DocumentPatch, _duplicate(), get_document(), list_documents() (+15 more)

### Community 13 - "PDF Layout Grouper"
Cohesion: 0.09
Nodes (7): Line, Grouper, inline_points(), Label, num(), Pos, test_inline_points_in_question()

### Community 14 - "test_api.py"
Cohesion: 0.17
Nodes (17): _interact(), answer_blocks(), connect_message(), esc(), _exam_link(), _header(), _images(), message() (+9 more)

### Community 15 - "test_mcp_tools.py"
Cohesion: 0.07
Nodes (45): exam_dir(), Attempt, match_solution(), mc_keys(), with_overrides(), _answer(), _applicable_context(), BadInput (+37 more)

### Community 16 - "GradingList.vue"
Cohesion: 0.03
Nodes (80): answer, COLORS, MODES, part(), parts, pen, props, setPart() (+72 more)

### Community 17 - "test_sync.py"
Cohesion: 0.08
Nodes (41): Exam, max_points(), age(), ans(), attempt_body(), exam(), full(), meta() (+33 more)

### Community 18 - "signed_in"
Cohesion: 0.07
Nodes (26): allowed(), primary_email(), signed_in(), fake_identity(), test_account_exam_only_visible_to_owner(), test_allowed_is_open_without_list(), test_allowed_matches_case_insensitively(), test_callback_accepts_listed_email() (+18 more)

### Community 19 - "Frontend CI Workflow"
Cohesion: 0.05
Nodes (43): name, permissions, runs-on, steps, CI, NODE_ENV, jobs, build-test-deploy (+35 more)

### Community 20 - "ResultsView.vue"
Cohesion: 0.09
Nodes (25): account, askLlm(), compare(), dropOpen, error, grade(), gradeMyself(), gradeParams() (+17 more)

### Community 21 - "Grading Errors and Streaming"
Cohesion: 0.21
Nodes (28): Thinking, stream(), stream(), aio(), anth(), install(), chunk(), collect() (+20 more)

### Community 22 - "Phase 5b-1 handoff: Anki export"
Cohesion: 0.50
Nodes (3): Decisions already made, Not done, Phase 5b-1 handoff: Anki export

### Community 23 - "settings"
Cohesion: 0.12
Nodes (22): llm_schema(), walk(), LlmLine, Part, _png(), Reference, RubricLine, Solution (+14 more)

### Community 24 - "test_rag_slides.py"
Cohesion: 0.11
Nodes (19): DeckPage, _lexical(), _match(), search_slides(), _similarity(), SlideHit, _unique(), _Unit (+11 more)

### Community 25 - "Text Enrichment"
Cohesion: 0.11
Nodes (25): available(), _center_in(), _digits(), _digits_latex(), enrich(), enrich_pages(), Enriched, find_items() (+17 more)

### Community 26 - "grading.ts"
Cohesion: 0.07
Nodes (44): error, loading, open, props, request, show(), request, isAnswered() (+36 more)

### Community 27 - "MC Detection"
Cohesion: 0.15
Nodes (20): Word, answer_key(), _area(), _bbox(), candidates(), _center(), find_options(), _in_row() (+12 more)

### Community 28 - "test_notion_client.py"
Cohesion: 0.21
Nodes (23): create_page(), body(), mock(), h(), test_401_is_notion_auth(), test_404_is_notion_gone(), test_429_waits_retry_after_then_succeeds(), test_archived_parent_is_notion_gone() (+15 more)

### Community 29 - "exam.ts"
Cohesion: 0.03
Nodes (76): emit, clamp(), emit, Hit, hit(), hits, pct(), props (+68 more)

### Community 30 - "test_chats.py"
Cohesion: 0.15
Nodes (11): chatter(), llm(), fake(), pin_first_slide(), test_ai_turn_errors(), test_ai_turn_holds_no_db_connection_while_the_llm_answers(), test_ai_turn_sends_only_pinned_pages_and_the_last_messages_and_cites_only_pins(), test_another_users_chat_is_404() (+3 more)

### Community 31 - "build_card"
Cohesion: 0.28
Nodes (19): _block(), build_card(), _cap(), _image(), _rich(), _select(), a(), q() (+11 more)

### Community 32 - "useAttemptStore"
Cohesion: 0.05
Nodes (75): Task 7: Frontend and docs, boxed, plain, region, setup(), W, setup(), structure (+67 more)

### Community 33 - "make_pdf"
Cohesion: 0.27
Nodes (10): read_deck(), _esc(), L, make_pdf(), footer(), structured(), test_a_deck_without_structure_still_has_its_text(), test_a_label_every_page_shares_is_not_a_slide_number() (+2 more)

### Community 34 - "deck.py"
Cohesion: 0.10
Nodes (13): RateLimiter, events(), fake(), install(), lookups(), test_error_event(), test_exclude_exams_must_be_at_most_ten_uuids(), test_exclude_exams_reach_the_material_lookup() (+5 more)

### Community 35 - "hints.py"
Cohesion: 0.15
Nodes (8): hints(), _spellings(), Vocab, vocabulary(), tokens(), test_hint_spelling_tie_goes_to_the_first_seen(), test_hints_handle_umlauts_and_return_the_slide_spelling(), _vocab()

### Community 36 - "test_slack_events.py"
Cohesion: 0.09
Nodes (32): WebhookEvent, collect(), main(), write_report(), sign(), verified_body(), verify(), cleanup() (+24 more)

### Community 37 - "test_anki.py"
Cohesion: 0.07
Nodes (39): build_deck(), course_id(), latest_shares(), weak_refs(), anki(), deck(), http(), test_below_out_of_range_is_422() (+31 more)

### Community 38 - "Documents Client API"
Cohesion: 0.13
Nodes (20): patchDocument(), account, chatId, decks, decksOf(), file(), load(), manageError (+12 more)

### Community 39 - "notion/client.py"
Cohesion: 0.23
Nodes (5): _call(), create_database(), refresh(), _select(), upload_image()

### Community 40 - "test_grading.py"
Cohesion: 0.23
Nodes (17): Final, fake(), install(), req(), run(), test_adapter_error_code_passes_through(), test_basis_follows_solution(), test_invalid_json_is_llm_failed() (+9 more)

### Community 41 - "Sub/Superscript Folding"
Cohesion: 0.25
Nodes (22): _baseline(), fold_scripts(), near(), ch(), line(), test_big_operator_font_base(), test_clean_fold_before_gap_still_folds(), test_digit_right_after_label_not_folded() (+14 more)

### Community 42 - "Job"
Cohesion: 0.20
Nodes (22): Job, claim(), run_once(), test_job_stream_gives_up_on_a_stuck_job(), add_job(), exam_of(), fake_pipeline(), queue_deck() (+14 more)

### Community 43 - "structure.py"
Cohesion: 0.08
Nodes (33): process(), _redact_map(), render_variants(), _f(), parse_duration(), parse_mc_rule(), AnswerBox, Context (+25 more)

### Community 44 - "MCP Tokens UI"
Cohesion: 0.14
Nodes (16): command, copy(), create(), error, fresh, name, refresh(), revoke() (+8 more)

### Community 45 - "outline.py"
Cohesion: 0.18
Nodes (13): PageRead, AiEntry, AiOutline, AiSection, _blocks(), _bookmarks(), _footer(), from_ai() (+5 more)

### Community 46 - "Course"
Cohesion: 0.20
Nodes (9): create_subject(), download_anki(), list_subjects(), _name(), queue_notion_export(), rename_subject(), SubjectIn, SubjectOut (+1 more)

### Community 47 - "test_eval_scans.py"
Cohesion: 0.07
Nodes (62): GradingBox, Page, _b64(), build_cases(), _contact_sheet(), _file_b64(), find_pairs(), _import_one() (+54 more)

### Community 48 - "json"
Cohesion: 0.18
Nodes (9): features(), main(), run(), run_all(), summarize(), main(), summary(), test_issue_messages_are_grouped_by_kind() (+1 more)

### Community 49 - "test_visual.py"
Cohesion: 0.27
Nodes (21): Box, line(), test_big_operator_visual(), test_code_is_text_with_indent(), test_control_and_private_use_glyphs_visual(), test_converted_table_is_text(), test_figures_are_visual(), test_fraction_bar_visual() (+13 more)

### Community 50 - "StudyView.vue"
Cohesion: 0.10
Nodes (22): AskError, askErrorMessage(), improveOutline(), resetOutline(), busy, change(), confirming, decks (+14 more)

### Community 51 - "Task 5: The exporter"
Cohesion: 0.20
Nodes (17): NotionAuth, NotionError, NotionGone, cards(), run(), test_401_refreshes_and_stores_rotated_tokens(), test_deleted_database_is_recreated_once(), test_expiring_token_is_refreshed_first() (+9 more)

### Community 52 - "FakeStream"
Cohesion: 0.12
Nodes (8): client(), stream(), Client, FakeOStream, FakeStream, install(), client(), create()

### Community 53 - "test_grading_api.py"
Cohesion: 0.08
Nodes (25): always_online, display_name, display_information, name, bot_events, request_url, features, bot_user (+17 more)

### Community 54 - "NotionIntegration.vue"
Cohesion: 0.09
Nodes (24): connections, databaseUrl, disconnect(), enabled, error, notice, run(), connections (+16 more)

### Community 56 - "test_integrations.py"
Cohesion: 0.15
Nodes (31): load(), decrypt(), connect(), fake_exchange(), ex(), fake_notion(), notion_connect(), notion_on() (+23 more)

### Community 57 - "watch"
Cohesion: 0.13
Nodes (18): context, dockerfile, watch, services, vuejs-dev, vuejs-prod, vuejs-test, build (+10 more)

### Community 58 - "test_rag_outline.py"
Cohesion: 0.28
Nodes (15): build_outline(), pages(), shape(), test_a_footer_seen_once_is_not_structure(), test_ai_outline_errors_and_ownership(), test_ai_outline_holds_no_db_connection_while_the_llm_answers(), test_ai_outline_sends_titles_and_openings_replaces_and_resets(), test_an_upload_stores_the_outline_with_its_source() (+7 more)

### Community 59 - "devDependencies"
Cohesion: 0.11
Nodes (18): devDependencies, fake-indexeddb@^6.2.6, jiti@^2.6.1, jsdom@^29.0.2, oxlint@~1.60.0, prettier@3.8.3, @tsconfig/node24@^24.0.4, vitest@^4.1.4 (+10 more)

### Community 60 - "test_slack_crops.py"
Cohesion: 0.27
Nodes (11): crop_file(), crop_url(), crop(), test_bad_tokens_return_none(), test_missing_file_returns_none(), test_round_trip(), test_route_404_when_slack_disabled(), test_route_serves_png_and_404s_everything_else() (+3 more)

### Community 61 - "api/sync.py"
Cohesion: 0.13
Nodes (14): list_integrations(), conns(), _decode_crops(), _end_auth_transaction(), _once_more_on_conflict(), put_attempt(), put_exam(), _put_exam() (+6 more)

### Community 62 - "db"
Cohesion: 0.12
Nodes (16): environment, healthcheck, image, ports, volumes, POSTGRES_DB, POSTGRES_PASSWORD, POSTGRES_USER (+8 more)

### Community 63 - "grader.py"
Cohesion: 0.12
Nodes (24): finalize(), grade(), _grade_events(), grade_stream(), GradingError, _image_count(), GradeIn, GradeOut (+16 more)

### Community 64 - "ExamSettingsView.vue"
Cohesion: 0.04
Nodes (39): router, route, exam, ink, route, attendance, canStart, error (+31 more)

### Community 65 - "scoring.ts (mcPoints, scores, changedInOvertime)"
Cohesion: 0.14
Nodes (11): GradingList and PointsPicker (solution/self grading), Pipeline MC options and answer key (mc.py), scoring.ts (mcPoints, scores, changedInOvertime), Editable points (pointOverrides), Spec: Frontend Core Loop Design, Attendance check modal, Multiple choice ticked directly on the crop, Spec: Phase 3a Auth + two-way sync (+3 more)

### Community 66 - "test_notion_export.py"
Cohesion: 0.21
Nodes (13): enabled(), http(), notion(), post(), test_disabled_is_404(), test_foreign_subject_is_404(), test_needs_login(), test_post_nothing_weak_is_409() (+5 more)

### Community 67 - "ChatPane.spec.ts"
Cohesion: 0.21
Nodes (13): calls, chatNow(), create(), exams, fakeServer(), json(), messages(), pinned (+5 more)

### Community 68 - "deck.py"
Cohesion: 0.15
Nodes (6): _accent(), _bookmarks(), _read_page(), clean(), test_clean_repairs_extraction_damage(), test_tokens_ignore_case_umlaut_spelling_and_hyphens()

### Community 69 - "server.py"
Cohesion: 0.16
Nodes (8): find_tasks(), get_task(), list_subjects(), my_history(), progress(), record_practice(), _run(), set_points()

### Community 70 - "test_slack_quiz.py"
Cohesion: 0.13
Nodes (35): question_blocks(), alltext(), ask(), click(), crops(), post(), _task(), test_answer_blocks_stay_under_50() (+27 more)

### Community 71 - "conftest.py"
Cohesion: 0.16
Nodes (5): database(), db(), enrich_calls(), fake_embed(), open_sign_in()

### Community 72 - "AddMaterial.vue"
Cohesion: 0.07
Nodes (36): account, add(), chain, emit, error, existing, kind, pending (+28 more)

### Community 73 - "index.py"
Cohesion: 0.20
Nodes (5): split(), backfill_decks(), store_deck(), test_split_cuts_a_single_huge_line_and_skips_blanks(), test_split_packs_lines_and_respects_limit()

### Community 74 - "ExamModals.vue"
Cohesion: 0.22
Nodes (8): Anti-goals, Approaches, Constraints, Decisions left to the builder, Goals, Intent, Non-goals, Phase 5a: integrations + Slack (design)

### Community 75 - "package.json"
Cohesion: 0.13
Nodes (14): npm-run-all2@^8.0.4, @types/jsdom@^28.0.1, @types/node@^24.12.2, typescript@~6.0.0, engines, node, name, private (+6 more)

### Community 76 - "PdfViewer.vue"
Cohesion: 0.21
Nodes (10): canvas, draw(), emit, escape(), highlighter(), mark(), props, textBox (+2 more)

### Community 77 - "test_api.py"
Cohesion: 0.24
Nodes (12): needs(), post(), process(), test_corrupt_pdf_is_unreadable(), test_events_stream_ends_with_final_state(), test_exam_upload(), test_job_stream_keeps_following_a_job_that_beats(), test_role_solution_adds_solution_images() (+4 more)

### Community 78 - "uuid"
Cohesion: 0.20
Nodes (16): client(), new_token(), rpc(), test_mcp_accepts_browser_origin_but_api_writes_stay_same_origin(), test_mcp_accepts_proxied_host(), test_mcp_bad_token_is_401(), test_mcp_lists_tools_at_exact_path(), test_mcp_revoked_token_is_401() (+8 more)

### Community 79 - "Term-weighted search blended with embeddings"
Cohesion: 0.18
Nodes (11): RAG eval cases (backend/evals/rag/cases.json), Search spike result (hit@1/hit@5), Optional deck structure signals (bookmarks, title size, footer, accent), Term-weighted search blended with embeddings, AI turn, Chat, Deck, Material (+3 more)

### Community 80 - "current_user dependency (401)"
Cohesion: 0.24
Nodes (11): current_user dependency (401), GET /api/sync with cursor and overlap, PUT /api/attempts/{id} (attempts.py), PUT /api/exams/{id}, lib/sync.ts push/pull client, Plan: MCP Server, Personal access tokens (AccessToken, /api/tokens), BearerAuth ASGI wrapper (+3 more)

### Community 81 - "scripts"
Cohesion: 0.18
Nodes (11): scripts, build, build-only, dev, format, lint, lint:eslint, lint:oxlint (+3 more)

### Community 82 - "eslint.config.ts"
Cohesion: 0.15
Nodes (12): eslint@^10.2.1, eslint-config-prettier@^10.1.8, eslint-plugin-oxlint@~1.60.0, eslint-plugin-vue@~10.8.0, @vitest/eslint-plugin@^1.6.16, @vue/eslint-config-typescript@^14.7.0, eslint, eslint-config-prettier (+4 more)

### Community 83 - "process"
Cohesion: 0.21
Nodes (5): upload_path(), JobFailed, process(), process_document(), _stage()

### Community 84 - "Slack /quiz: page crops, kept question, self-check (design)"
Cohesion: 0.10
Nodes (18): respond(), test_respond_logs_body_on_error(), test_respond_refuses_other_hosts(), Closed, Decisions already made, Known limits, Later changes (after the first handoff), Not done (+10 more)

### Community 85 - "exam-sim project"
Cohesion: 0.29
Nodes (7): exam-sim project, Ask redesign (chat, no code yet), Domain docs consumption guide, GitHub issue tracker conventions, Triage label vocabulary, Open findings log, Subject

### Community 86 - "grader.py (grade_stream, finalize, GradingError)"
Cohesion: 0.22
Nodes (9): Plan: LLM Grading + Eval, Grading eval runner (run_eval.py, metrics), Google AI Studio grading adapter, grader.py (grade_stream, finalize, GradingError), OpenRouter grading adapter, Provider-neutral prompt items (Text, Image, CacheBreak), Spec: LLM grading + eval (three providers), Grading basis: solution guide vs own solution (+1 more)

### Community 87 - "Plan: Phase 3a Auth + Sync"
Cohesion: 0.20
Nodes (9): Plan: Phase 1 Subject Names, course_id find-or-create helper, guessSubject rewrite, jobs.subject column, Plan: Phase 3a Auth + Sync, Sync wire format (ExamMeta, AttemptWire, SyncOut), Spec: Phase 1 Subject names, courses table as Subject (+1 more)

### Community 88 - "dependencies"
Cohesion: 0.17
Nodes (12): dependencies, idb@^8.0.4, pdfjs-dist@^6.5.438, pinia@^3.0.4, @primeuix/themes@^2.0.3, primevue@^4.5.5, vue@^3.5.32, vue-router@^5.0.4 (+4 more)

### Community 89 - "api/auth.py"
Cohesion: 0.06
Nodes (37): callback(), create_token(), current_user(), delete_token(), _hash(), identity(), list_tokens(), login() (+29 more)

### Community 90 - "tsconfig.app.json"
Cohesion: 0.22
Nodes (8): compilerOptions, noUncheckedIndexedAccess, paths, tsBuildInfoFile, exclude, extends, include, @vue/tsconfig/tsconfig.dom.json

### Community 91 - "tsconfig.vitest.json"
Cohesion: 0.22
Nodes (8): compilerOptions, lib, tsBuildInfoFile, types, exclude, extends, include, ./tsconfig.app.json

### Community 92 - "StatisticsView.vue"
Cohesion: 0.03
Nodes (103): emit, open, props, rename(), solution, any, lines, props (+95 more)

### Community 93 - "environment"
Cohesion: 0.34
Nodes (20): environment, ALLOWED_EMAILS, DATABASE_URL, FASTEMBED_CACHE_PATH, GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET (+12 more)

### Community 94 - "Hybrid search (tsvector + pgvector RRF)"
Cohesion: 0.32
Nodes (8): Plan: Phase 4 RAG Ask + slides per subject, documents and chunks tables, Local fastembed multilingual embeddings, Hybrid search (tsvector + pgvector RRF), Spec: Phase 4b Ask as Chat over Decks, Deck Outline (automatic and AI), Per-page structure extraction (label, title, headings, footer), Term-weighted BM25-style Search with embedding blend

### Community 95 - "vite.config.ts"
Cohesion: 0.25
Nodes (6): vite@^8.0.8, vite-plugin-vue-devtools@^8.1.1, @vitejs/plugin-vue@^6.0.6, vite, vite-plugin-vue-devtools, @vitejs/plugin-vue

### Community 96 - "vue"
Cohesion: 0.05
Nodes (46): route, account, accountOpen, providerNames, settingsOpen, account, keyAt, modelOptions (+38 more)

### Community 98 - "interactions"
Cohesion: 0.19
Nodes (11): _command(), commands(), events(), _form(), _handle(), interactions(), Global Constraints, Phase 5a: integrations + Slack Implementation Plan (+3 more)

### Community 99 - "api/ask.py"
Cohesion: 0.26
Nodes (5): lookup(), LookupIn, search_hints(), search_subject(), SearchIn

### Community 100 - "LLM grading core (solution-first)"
Cohesion: 0.33
Nodes (6): Grading eval runner, Eval metrics (exact, in_range, mae, calibration), POST /api/grade, Grading eval runner (run_eval), LLM grading core (solution-first), Three LLM providers (Anthropic, Google, OpenRouter)

### Community 101 - "RAG Ask (phase 4)"
Cohesion: 0.33
Nodes (6): Postgres data model and Alembic, documents and chunks tables (pgvector), Hybrid search (vector + full-text, RRF), Local fastembed MiniLM embeddings, RAG Ask (phase 4), Where to read this lookup

### Community 102 - "Two-way sync (exams and attempts)"
Cohesion: 0.29
Nodes (6): OAuth login and server sessions, course_id() find-or-create course, guessSubject filename heuristic, Client outbox and sync.ts, PUT exams/attempts and GET /api/sync routes, Two-way sync (exams and attempts)

### Community 103 - "Plan: Frontend Core Loop"
Cohesion: 0.29
Nodes (6): Plan: Frontend Core Loop, Pinia attempt store (clock, snapshot, persistence), IndexedDB access layer (db.ts), POST /api/exams stateless upload endpoint, Client edit times and dirty outbox (db.ts), Offline-first: browser as working copy

### Community 104 - "Spec: Phase 2b Text-first grading inputs"
Cohesion: 0.29
Nodes (6): Pipeline duration and MC rule parsing (meta.py), Plan: Text-first Grading Inputs, Points derivation rules (structure.py), MC scoring rule (per tick or all-or-nothing), Spec: Phase 2b Text-first grading inputs, Two-value points split rule

### Community 105 - "X-LLM-Key header (never stored or logged)"
Cohesion: 0.33
Nodes (5): Anthropic grading adapter, X-LLM-Key header (never stored or logged), POST /api/ask with validated citations, Saved Chat per Subject, Pinned pages sent to AI turn

### Community 106 - ".oxlintrc.json"
Cohesion: 0.29
Nodes (6): categories, correctness, env, browser, plugins, $schema

### Community 107 - "NotionDatabase"
Cohesion: 0.41
Nodes (9): NotionCard, NotionDatabase, notion_job(), setup_rows(), test_card_key_is_unique(), test_cards_cascade_with_integration_and_exam(), test_job_kind_notion_is_accepted(), test_one_active_notion_job_per_course() (+1 more)

### Community 108 - "PdfDropZone.vue"
Cohesion: 0.38
Nodes (6): dragging, emit, input, onChange(), onDrop(), props

### Community 109 - "Phase 5b: flashcard export, Anki first, then Notion (design)"
Cohesion: 0.18
Nodes (10): 5b-2 Notion (brainstormed 2026-11-25), Anti-goals, Approaches, Constraints, Decisions left to the builder, Goals (5b-1), Intent, Non-goals (+2 more)

### Community 110 - "FakeClient"
Cohesion: 0.18
Nodes (6): fake_provider(), FakeClient, test_github_emails_failure_redirects_to_login_failed(), test_github_identity_uses_verified_primary_not_public_email(), test_google_identity_drops_unverified_email(), test_signed_out_upload_is_refused_before_the_body_is_read()

### Community 111 - "Exam-sim upgrade roadmap"
Cohesion: 0.33
Nodes (6): Postgres job queue (SKIP LOCKED) and worker, Inbound Slack webhook (planned), SSE job progress, Phase 5: agent, Slack/Notion, webhooks (planned), Pipeline repair agent (planned), Exam-sim upgrade roadmap

### Community 112 - "MCP server at /mcp"
Cohesion: 0.47
Nodes (5): Personal access tokens (hashed, Bearer), MCP server at /mcp, record_practice (practice = attempt), Use exam-sim from Claude (MCP), MCP tools (list_subjects, progress, find_tasks, get_task, my_history, record_practice, set_points)

### Community 113 - "Client grading library (planGrading, streamGrade)"
Cohesion: 0.33
Nodes (6): Attempt store LLM run/stop/rubric saving, Client grading library (planGrading, streamGrade), POST /api/grade route with RateLimiter, LlmCard and LlmSummary UI, POST /api/materials/lookup (where to read this), LLM card layout per subtask

### Community 115 - "Fake"
Cohesion: 0.38
Nodes (3): ex(), Fake, fake()

### Community 116 - "Text-first grading inputs"
Cohesion: 0.50
Nodes (4): Docling enrichment (formulas as LaTeX), fold_scripts (sub/superscripts into text), Points extraction rules and mc_rule, Text-first grading inputs

### Community 117 - ".prettierrc.json"
Cohesion: 0.40
Nodes (4): printWidth, $schema, semi, singleQuote

### Community 118 - "select"
Cohesion: 0.07
Nodes (33): get_sync(), from_rows(), _pick(), to_rows(), Base, Chunk, Subtask, Task (+25 more)

### Community 119 - "docling enrichment (enrich.py)"
Cohesion: 0.50
Nodes (3): docling enrichment (enrich.py), fold_scripts sub/superscripts, visual() region rule

### Community 124 - "db/models.py"
Cohesion: 0.08
Nodes (17): _html(), _imgs(), encrypt(), _fernet(), created(), Integration, updated(), key() (+9 more)

### Community 131 - "export.py"
Cohesion: 0.22
Nodes (10): _database(), export_subject(), lock_key(), _send(), test_each_card_beats_and_the_worker_bumps_locked_at(), spy(), test_exports_of_one_connection_wait_for_each_other(), other() (+2 more)

### Community 132 - "Review Focus"
Cohesion: 0.33
Nodes (5): Global Constraints, Review Focus, Slack /quiz crops Implementation Plan, Task 3: Gate — one real question in Slack (manual, throwaway), Task 5: Self-check buttons

### Community 133 - "step"
Cohesion: 0.20
Nodes (6): guarded_step(), main(), step(), test_a_failing_loop_step_is_survived(), boom(), test_unreadable_pdf_still_removes_the_deck()

### Community 134 - "FakeGStream"
Cohesion: 0.31
Nodes (4): FakeGStream, install(), client(), gen()

### Community 135 - "conftest.py"
Cohesion: 0.09
Nodes (31): extract(), group(), measure(), _tokens(), category(), main(), _one(), points_report() (+23 more)

### Community 137 - "test_subjects.py"
Cohesion: 0.36
Nodes (6): names(), test_create_is_empty_idempotent_and_case_insensitive(), test_list_includes_exam_only_deck_only_and_empty_subjects(), test_other_users_subjects_are_invisible(), test_rename_follows_decks_and_exams_and_rejects_duplicates(), user()

### Community 138 - "ExamModals.vue"
Cohesion: 0.29
Nodes (5): handIn(), remaining, route, router, store

### Community 139 - "ExportFailed"
Cohesion: 0.40
Nodes (3): ExportFailed, test_worker_maps_export_failed_to_error_code(), fail()

### Community 140 - "SubjectSelect.vue"
Cohesion: 0.21
Nodes (15): Task 4: Button and docs, commit(), emit, library, model, names, options, createSubject() (+7 more)

### Community 142 - "PdfDropZone.vue"
Cohesion: 0.40
Nodes (4): Decisions already made (don't revisit), Done, Not done, Phase 5a Slack: status and what's left

### Community 143 - "services"
Cohesion: 0.11
Nodes (17): internal, networks, backend, edge, tunnel, services, web, build (+9 more)

### Community 145 - "test_slack_events.py"
Cohesion: 0.40
Nodes (4): Anki export, Import, Not exported, What is in the deck

### Community 147 - "db"
Cohesion: 0.12
Nodes (17): cap_add, cap_drop, environment, healthcheck, image, networks, restart, security_opt (+9 more)

### Community 148 - "x-backend-env"
Cohesion: 0.12
Nodes (17): x-backend-env, ALLOWED_EMAILS, DATABASE_URL, FASTEMBED_CACHE_PATH, GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET (+9 more)

### Community 149 - "Modal.vue"
Cohesion: 0.47
Nodes (5): emit, onKeydown(), panel, props, requestClose()

### Community 151 - "MaterialView.spec.ts"
Cohesion: 0.50
Nodes (4): docs, json(), open(), viewer

### Community 153 - "api"
Cohesion: 0.15
Nodes (13): build, cap_drop, command, depends_on, image, networks, restart, security_opt (+5 more)

### Community 162 - "migrate"
Cohesion: 0.17
Nodes (12): condition, db, build, cap_drop, command, depends_on, image, networks (+4 more)

### Community 163 - "worker"
Cohesion: 0.18
Nodes (11): worker, build, cap_drop, command, cpus, image, mem_limit, networks (+3 more)

### Community 164 - "Quiz yourself from Slack"
Cohesion: 0.33
Nodes (5): Disconnect, Page crops in messages, Quiz yourself from Slack, Set up, What `/quiz` does

### Community 166 - "Flashcards in Notion"
Cohesion: 0.25
Nodes (7): Flashcards in Notion, Manual check (open), Rules, Set up, What you get, Global Constraints, Subject

### Community 169 - "cloudflared"
Cohesion: 0.22
Nodes (9): cap_drop, command, environment, image, networks, restart, security_opt, TUNNEL_TOKEN (+1 more)

### Community 170 - "x-backend"
Cohesion: 0.29
Nodes (7): x-backend, build, cap_drop, image, restart, security_opt, volumes

## Knowledge Gaps
- **34 isolated node(s):** `exam-sim-backend`, `@vue/tsconfig/tsconfig.dom.json`, `./tsconfig.app.json`, `Eval metrics (exact, in_range, mae, calibration)`, `Where to read this lookup` (+29 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1293 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **20 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Subject` connect `Flashcards in Notion` to `SubjectSelect.vue`, `Documents Client API`?**
  _High betweenness centrality (0.252) - this node is a cross-community bridge._
- **Are the 59 inferred relationships involving `User` (e.g. with `lookup()` and `search_hints()`) actually correct?**
  _`User` has 59 INFERRED edges - model-reasoned connections that need verification._
- **What connects `exam-sim-backend`, `@vue/tsconfig/tsconfig.dom.json`, `./tsconfig.app.json` to the rest of the system?**
  _34 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `stores/attempt.ts` be split into smaller, more focused modules?**
  _Cohesion score 0.07641196013289037 - nodes in this community are weakly interconnected._
- **Why does `Exam` connect `test_sync.py` to `test_mcp_tools.py`, `test_slack_events.py`, `api/sync.py`, `test_slack_quiz.py`, `Flashcards in Notion`, `index.py`, `routes.py`, `NotionDatabase`, `Job`, `Course`, `test_mcp_tools.py`, `select`, `db/models.py`, `api/sync.py`?**
  _High betweenness centrality (0.233) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `signed_in()` (e.g. with `fake_identity()` and `Task 3: Connect, list and disconnect Slack (OAuth)`) actually correct?**
  _`signed_in()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Should `test_mcp_tools.py` be split into smaller, more focused modules?**
  _Cohesion score 0.12091038406827881 - nodes in this community are weakly interconnected._