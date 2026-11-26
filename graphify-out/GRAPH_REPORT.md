# Graph Report - exam-sim  (2026-11-26)

## Corpus Check
- 284 files · ~214,035 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 18 file(s) not represented in the graph (top: (none) 9, .example 2, .graphify-bak 1)

## Summary
- 3653 nodes · 10069 edges · 149 communities (131 shown, 18 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 892 edges (avg confidence: 0.92)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `619e6348`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- stores/attempt.ts
- Attempt
- db.ts
- sqlalchemy
- chats.py
- test_rag_outline.py
- Chat Pane
- NewExamView.vue
- extract.py
- signed_in
- grading.ts
- Pipeline Task Model and MC
- User
- PDF Layout Grouper
- test_api.py
- select
- GradingList.vue
- test_sync.py
- test_auth.py
- Frontend CI Workflow
- ResultsView.vue
- Grading Errors and Streaming
- test_slack_crops.py
- settings
- test_api.py
- Text Enrichment
- exam.ts
- MC Detection
- test_notion_export.py
- api/auth.py
- test_slack_events.py
- McRule
- useAttemptStore
- Exam
- deck.py
- MaterialView.vue
- verify
- test_anki.py
- Documents Client API
- build_card
- test_grading.py
- Sub/Superscript Folding
- worker/main.py
- render.py
- MCP Tokens UI
- conftest.py
- quiz.py
- job_events
- GradingError
- test_visual.py
- StudyView.vue
- test_unreadable_pdf_still_removes_the_deck
- FakeStream
- test_grading_api.py
- NotionIntegration.vue
- db/models.py
- LlmCard.vue
- watch
- McOverlay.vue
- devDependencies
- json
- FakeStream
- db
- grader.py
- ExamSettingsView.vue
- scoring.ts (mcPoints, scores, changedInOvertime)
- AppFrame.vue
- ChatPane.spec.ts
- routes.py
- LlmCard.vue
- test_slack_quiz.py
- worker/main.py
- test_slack_crops.py
- exam_dir
- ExamModals.vue
- package.json
- PdfViewer.vue
- server.py
- FakeClient
- Term-weighted search blended with embeddings
- current_user dependency (401)
- scripts
- eslint.config.ts
- scoring.py
- features
- exam-sim project
- grader.py (grade_stream, finalize, GradingError)
- Plan: Phase 3a Auth + Sync
- dependencies
- choice
- tsconfig.app.json
- tsconfig.vitest.json
- StatisticsView.vue
- environment
- Hybrid search (tsvector + pgvector RRF)
- vite.config.ts
- question_blocks
- interactions
- test_rag_slides.py
- LLM grading core (solution-first)
- RAG Ask (phase 4)
- Two-way sync (exams and attempts)
- Plan: Frontend Core Loop
- Spec: Phase 2b Text-first grading inputs
- X-LLM-Key header (never stored or logged)
- .oxlintrc.json
- PdfDropZone.vue
- MaterialView.spec.ts
- Exam-sim upgrade roadmap
- MCP server at /mcp
- Client grading library (planGrading, streamGrade)
- Text-first grading inputs
- .prettierrc.json
- docling enrichment (enrich.py)
- tsconfig.json
- pipeline-smoke.sh
- Iframe browser PDF viewer with #page=N
- frontend README (Vue 3 Vite template)
- Testing levels (pipeline smoke test)
- exam-sim-backend
- fixture
- conftest.py
- SubjectSelect.vue
- PdfDropZone.vue
- services
- split
- test_slack_events.py
- test_chats.py
- db
- x-backend-env
- quiz.py
- invite_only_uploads
- api
- httpx
- migrate
- worker
- Quiz yourself from Slack
- Flashcards in Notion
- Review Focus
- cloudflared
- x-backend
- features
- test_numprog_integration

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

## Communities (149 total, 18 thin omitted)

### Community 0 - "stores/attempt.ts"
Cohesion: 0.07
Nodes (34): handIn(), remaining, route, router, store, store, group, GROUPS (+26 more)

### Community 1 - "Attempt"
Cohesion: 0.12
Nodes (15): _decode_crops(), _end_auth_transaction(), get_sync(), _once_more_on_conflict(), put_attempt(), _put_attempt(), put_exam(), _put_exam() (+7 more)

### Community 2 - "db.ts"
Cohesion: 0.06
Nodes (74): account, keyAt, modelOptions, modes, providers, settings, drop(), migrateAnswer() (+66 more)

### Community 3 - "sqlalchemy"
Cohesion: 0.07
Nodes (16): run_migrations_offline(), run_migrations_online(), upgrade(), upgrade(), upgrade(), upgrade(), upgrade(), upgrade() (+8 more)

### Community 4 - "chats.py"
Cohesion: 0.07
Nodes (23): ask_preview(), ask_turn(), AskTurnIn, delete_chat(), get_chat(), MessageIn, _out(), _own() (+15 more)

### Community 5 - "test_rag_outline.py"
Cohesion: 0.06
Nodes (45): _accent(), _bookmarks(), PageRead, read_deck(), _read_page(), AiEntry, AiOutline, AiSection (+37 more)

### Community 6 - "Chat Pane"
Cohesion: 0.06
Nodes (52): askAi(), asking, busy, chat, chats, error, fresh(), hints (+44 more)

### Community 7 - "NewExamView.vue"
Cohesion: 0.07
Nodes (29): decode(), errorFor(), followJob(), JobEnd, send(), serverCodes, UploadError, UploadErrorCode (+21 more)

### Community 8 - "extract.py"
Cohesion: 0.16
Nodes (14): base_font(), drop_margin_graphics(), key(), margin(), near_edge(), extract_page(), find_grading_boxes(), glyph_checkboxes() (+6 more)

### Community 9 - "signed_in"
Cohesion: 0.12
Nodes (29): signed_in(), stored_uploads(), test_a_lost_insert_race_answers_like_a_duplicate(), test_deck_over_the_cap_is_413(), test_decks_keep_upload_order_and_unfiled_ones_can_be_assigned(), test_delete_removes_chunks_and_file(), test_exam_upload_cleans_nul_from_filename(), test_foreign_documents_are_404() (+21 more)

### Community 10 - "grading.ts"
Cohesion: 0.07
Nodes (43): answered(), error, loading, open, props, request, show(), request (+35 more)

### Community 11 - "Pipeline Task Model and MC"
Cohesion: 0.12
Nodes (42): McOption, Task, apply_header_points(), derive_mc(), fill_remainder(), _half_step(), header_points(), HeaderPoints (+34 more)

### Community 12 - "User"
Cohesion: 0.13
Nodes (23): current_user(), list_chats(), _by_sha(), delete_document(), document_file(), DocumentOut, DocumentPatch, _duplicate() (+15 more)

### Community 13 - "PDF Layout Grouper"
Cohesion: 0.09
Nodes (12): Line, AnswerBox, Context, Issue, Region, Subtask, Grouper, inline_points() (+4 more)

### Community 14 - "test_api.py"
Cohesion: 0.26
Nodes (10): answer_blocks(), esc(), _exam_link(), _header(), _images(), _option(), _question_body(), _section() (+2 more)

### Community 15 - "select"
Cohesion: 0.05
Nodes (82): list_integrations(), conns(), _f(), _ids(), read_attempt(), subtask_keys(), write_attempt(), Answer (+74 more)

### Community 16 - "GradingList.vue"
Cohesion: 0.03
Nodes (79): answer, COLORS, MODES, part(), parts, pen, props, setPart() (+71 more)

### Community 17 - "test_sync.py"
Cohesion: 0.07
Nodes (43): check_declared(), _grade_request(), read_capped(), age(), ans(), attempt_body(), exam(), full() (+35 more)

### Community 18 - "test_auth.py"
Cohesion: 0.06
Nodes (31): allowed(), callback(), _hash(), identity(), logout(), primary_email(), start_session(), LoginSession (+23 more)

### Community 19 - "Frontend CI Workflow"
Cohesion: 0.05
Nodes (43): name, permissions, runs-on, steps, CI, NODE_ENV, jobs, build-test-deploy (+35 more)

### Community 20 - "ResultsView.vue"
Cohesion: 0.04
Nodes (56): ctxStub, draw(), fire(), pen, account, images(), keys, matches (+48 more)

### Community 21 - "Grading Errors and Streaming"
Cohesion: 0.21
Nodes (28): Thinking, stream(), stream(), aio(), anth(), install(), chunk(), collect() (+20 more)

### Community 22 - "test_slack_crops.py"
Cohesion: 0.27
Nodes (16): box(), needs(), subtasks(), test_answer_box_is_relative_to_its_region(), test_answer_box_split_over_two_pages_gives_one_box_per_region(), test_crops_stop_above_the_barcode_footer(), test_free_text_has_no_options(), test_key_from_solution_ink() (+8 more)

### Community 23 - "settings"
Cohesion: 0.13
Nodes (20): llm_schema(), walk(), LlmLine, Part, _png(), Reference, Solution, build_content() (+12 more)

### Community 24 - "test_api.py"
Cohesion: 0.22
Nodes (12): needs(), post(), process(), test_corrupt_pdf_is_unreadable(), test_events_stream_ends_with_final_state(), test_exam_upload(), test_job_stream_gives_up_on_a_stuck_job(), test_role_solution_adds_solution_images() (+4 more)

### Community 25 - "Text Enrichment"
Cohesion: 0.14
Nodes (19): _center_in(), _digits(), _digits_latex(), enrich_pages(), Enriched, find_items(), valid_latex(), Page (+11 more)

### Community 26 - "exam.ts"
Cohesion: 0.04
Nodes (58): emit, emit, hovered, jumpToContext(), pick(), store, tasks, view (+50 more)

### Community 27 - "MC Detection"
Cohesion: 0.17
Nodes (16): Word, answer_key(), _area(), _bbox(), candidates(), _center(), find_options(), _in_row() (+8 more)

### Community 28 - "test_notion_export.py"
Cohesion: 0.05
Nodes (63): _call(), create_database(), create_page(), NotionAuth, NotionError, NotionGone, refresh(), _select() (+55 more)

### Community 29 - "api/auth.py"
Cohesion: 0.04
Nodes (31): create_token(), delete_token(), invited_user(), list_tokens(), login(), me(), new_token(), optional_user() (+23 more)

### Community 30 - "test_slack_events.py"
Cohesion: 0.23
Nodes (13): slack_post(), add(), alive(), event(), post(), test_foreign_origin_is_refused_by_middleware_but_slack_sends_none(), test_malformed_body_is_400(), test_non_object_event_is_400() (+5 more)

### Community 31 - "McRule"
Cohesion: 0.16
Nodes (16): _f(), parse_duration(), parse_mc_rule(), McRule, per_tick_points(), test_all_or_nothing(), test_all_or_nothing_english(), test_duration() (+8 more)

### Community 32 - "useAttemptStore"
Cohesion: 0.04
Nodes (92): boxed, plain, region, setup(), W, setup(), structure, b() (+84 more)

### Community 33 - "Exam"
Cohesion: 0.07
Nodes (43): course_id(), from_rows(), _pick(), to_rows(), Base, Exam, Subtask, Task (+35 more)

### Community 34 - "deck.py"
Cohesion: 0.10
Nodes (14): RateLimiter, events(), fake(), install(), lookups(), test_error_event(), test_exclude_exams_must_be_at_most_ten_uuids(), test_exclude_exams_reach_the_material_lookup() (+6 more)

### Community 35 - "MaterialView.vue"
Cohesion: 0.07
Nodes (37): account, add(), chain, emit, error, existing, kind, pending (+29 more)

### Community 36 - "verify"
Cohesion: 0.31
Nodes (13): sign(), verified_body(), verify(), test_body_tampered_fails(), test_boundary_299s_passes(), test_future_timestamp_fails(), test_missing_or_garbage_inputs_fail(), test_non_ascii_body() (+5 more)

### Community 37 - "test_anki.py"
Cohesion: 0.07
Nodes (37): build_deck(), latest_shares(), weak_refs(), anki(), deck(), http(), test_below_out_of_range_is_422(), test_crops_replace_the_extracted_text() (+29 more)

### Community 38 - "Documents Client API"
Cohesion: 0.13
Nodes (20): patchDocument(), account, chatId, decks, decksOf(), file(), load(), manageError (+12 more)

### Community 39 - "build_card"
Cohesion: 0.28
Nodes (19): _block(), build_card(), _cap(), _image(), _rich(), _select(), a(), q() (+11 more)

### Community 40 - "test_grading.py"
Cohesion: 0.19
Nodes (19): Final, llm(), fake(), fake(), install(), req(), run(), test_adapter_error_code_passes_through() (+11 more)

### Community 41 - "Sub/Superscript Folding"
Cohesion: 0.25
Nodes (22): _baseline(), fold_scripts(), near(), ch(), line(), test_big_operator_font_base(), test_clean_fold_before_gap_still_folds(), test_digit_right_after_label_not_folded() (+14 more)

### Community 42 - "worker/main.py"
Cohesion: 0.17
Nodes (21): Job, claim(), add_job(), exam_of(), fake_pipeline(), queue_deck(), signed_in_user(), test_crash_requeues_the_job() (+13 more)

### Community 43 - "render.py"
Cohesion: 0.20
Nodes (9): _bluish(), _color(), crop(), _hide(), _in_any(), _is_solution_ink(), _is_watermark(), render_clean_page() (+1 more)

### Community 44 - "MCP Tokens UI"
Cohesion: 0.14
Nodes (16): command, copy(), create(), error, fresh, name, refresh(), revoke() (+8 more)

### Community 45 - "conftest.py"
Cohesion: 0.16
Nodes (5): database(), db(), enrich_calls(), fake_embed(), open_sign_in()

### Community 46 - "quiz.py"
Cohesion: 0.15
Nodes (12): _database(), export_subject(), ExportFailed, lock_key(), _send(), _Token, test_each_card_beats_and_the_worker_bumps_locked_at(), spy() (+4 more)

### Community 47 - "job_events"
Cohesion: 0.29
Nodes (4): job_events(), JobOut, _read_job(), test_job_stream_keeps_following_a_job_that_beats()

### Community 49 - "test_visual.py"
Cohesion: 0.24
Nodes (22): Box, line(), test_big_operator_visual(), test_code_is_text_with_indent(), test_control_and_private_use_glyphs_visual(), test_converted_table_is_text(), test_figures_are_visual(), test_fraction_bar_visual() (+14 more)

### Community 50 - "StudyView.vue"
Cohesion: 0.11
Nodes (21): askErrorMessage(), improveOutline(), resetOutline(), busy, change(), confirming, decks, error (+13 more)

### Community 51 - "test_unreadable_pdf_still_removes_the_deck"
Cohesion: 0.25
Nodes (5): guarded_step(), main(), test_a_failing_loop_step_is_survived(), boom(), test_unreadable_pdf_still_removes_the_deck()

### Community 52 - "FakeStream"
Cohesion: 0.12
Nodes (10): client(), Client, FakeGStream, FakeOStream, install(), client(), gen(), install() (+2 more)

### Community 53 - "test_grading_api.py"
Cohesion: 0.08
Nodes (25): always_online, display_name, display_information, name, bot_events, request_url, features, bot_user (+17 more)

### Community 54 - "NotionIntegration.vue"
Cohesion: 0.09
Nodes (24): connections, databaseUrl, disconnect(), enabled, error, notice, run(), connections (+16 more)

### Community 55 - "db/models.py"
Cohesion: 0.09
Nodes (26): create_subject(), download_anki(), list_subjects(), _name(), queue_notion_export(), rename_subject(), SubjectIn, SubjectOut (+18 more)

### Community 56 - "LlmCard.vue"
Cohesion: 0.15
Nodes (32): decrypt(), connect(), fake_exchange(), ex(), fake_notion(), notion_connect(), notion_on(), rows() (+24 more)

### Community 57 - "watch"
Cohesion: 0.13
Nodes (18): context, dockerfile, watch, services, vuejs-dev, vuejs-prod, vuejs-test, build (+10 more)

### Community 58 - "McOverlay.vue"
Cohesion: 0.36
Nodes (7): clamp(), emit, Hit, hit(), hits, pct(), props

### Community 59 - "devDependencies"
Cohesion: 0.11
Nodes (18): devDependencies, fake-indexeddb@^6.2.6, jiti@^2.6.1, jsdom@^29.0.2, oxlint@~1.60.0, prettier@3.8.3, @tsconfig/node24@^24.0.4, vitest@^4.1.4 (+10 more)

### Community 60 - "json"
Cohesion: 0.53
Nodes (4): call(), test_get_task_over_mcp_returns_images(), test_record_practice_over_mcp(), test_tools_over_mcp_are_bound_to_the_user()

### Community 62 - "db"
Cohesion: 0.12
Nodes (16): environment, healthcheck, image, ports, volumes, POSTGRES_DB, POSTGRES_PASSWORD, POSTGRES_USER (+8 more)

### Community 63 - "grader.py"
Cohesion: 0.14
Nodes (21): grade(), finalize(), grade(), _grade_events(), grade_stream(), _image_count(), GradeIn, GradeOut (+13 more)

### Community 64 - "ExamSettingsView.vue"
Cohesion: 0.09
Nodes (23): attendance, canStart, error, exam, examId, hasMc, included, issues (+15 more)

### Community 65 - "scoring.ts (mcPoints, scores, changedInOvertime)"
Cohesion: 0.14
Nodes (11): GradingList and PointsPicker (solution/self grading), Pipeline MC options and answer key (mc.py), scoring.ts (mcPoints, scores, changedInOvertime), Editable points (pointOverrides), Spec: Frontend Core Loop Design, Attendance check modal, Multiple choice ticked directly on the crop, Spec: Phase 3a Auth + two-way sync (+3 more)

### Community 66 - "AppFrame.vue"
Cohesion: 0.10
Nodes (15): route, account, accountOpen, providerNames, settingsOpen, collapsed, groups, narrow (+7 more)

### Community 67 - "ChatPane.spec.ts"
Cohesion: 0.21
Nodes (13): calls, chatNow(), create(), exams, fakeServer(), json(), messages(), pinned (+5 more)

### Community 68 - "routes.py"
Cohesion: 0.09
Nodes (15): _imgs(), _encode(), get_exam(), get_job(), upload_exam(), _visible(), _visible_job(), doc_dir() (+7 more)

### Community 69 - "LlmCard.vue"
Cohesion: 0.18
Nodes (8): model, points, props, shown, SKIPS, skipText, verdict(), LlmGrade

### Community 70 - "test_slack_quiz.py"
Cohesion: 0.17
Nodes (25): alltext(), ask(), click(), crops(), post(), test_answer_keeps_question_and_separates_solution(), test_answers(), test_bad_interaction_is_400() (+17 more)

### Community 71 - "worker/main.py"
Cohesion: 0.23
Nodes (6): JobFailed, process(), process_document(), run_once(), _stage(), step()

### Community 72 - "test_slack_crops.py"
Cohesion: 0.16
Nodes (18): encrypt(), _fernet(), crop_file(), crop_url(), key(), test_rotation(), test_round_trip(), test_ttl_rejects_old_token() (+10 more)

### Community 73 - "exam_dir"
Cohesion: 0.18
Nodes (10): 5b-2 Notion (brainstormed 2026-11-25), Anti-goals, Approaches, Constraints, Decisions left to the builder, Goals (5b-1), Intent, Non-goals (+2 more)

### Community 74 - "ExamModals.vue"
Cohesion: 0.22
Nodes (8): Anti-goals, Approaches, Constraints, Decisions left to the builder, Goals, Intent, Non-goals, Phase 5a: integrations + Slack (design)

### Community 75 - "package.json"
Cohesion: 0.13
Nodes (14): npm-run-all2@^8.0.4, @types/jsdom@^28.0.1, @types/node@^24.12.2, typescript@~6.0.0, engines, node, name, private (+6 more)

### Community 76 - "PdfViewer.vue"
Cohesion: 0.21
Nodes (10): canvas, draw(), emit, escape(), highlighter(), mark(), props, textBox (+2 more)

### Community 77 - "server.py"
Cohesion: 0.13
Nodes (9): BearerAuth, find_tasks(), get_task(), list_subjects(), my_history(), progress(), record_practice(), _run() (+1 more)

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

### Community 83 - "scoring.py"
Cohesion: 0.18
Nodes (8): _auto(), _is_mc(), match_solution(), max_points(), mc_keys(), mc_points(), subtask_scores(), with_overrides()

### Community 84 - "features"
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

### Community 90 - "tsconfig.app.json"
Cohesion: 0.22
Nodes (8): compilerOptions, noUncheckedIndexedAccess, paths, tsBuildInfoFile, exclude, extends, include, @vue/tsconfig/tsconfig.dom.json

### Community 91 - "tsconfig.vitest.json"
Cohesion: 0.22
Nodes (8): compilerOptions, lib, tsBuildInfoFile, types, exclude, extends, include, ./tsconfig.app.json

### Community 92 - "StatisticsView.vue"
Cohesion: 0.04
Nodes (92): emit, open, props, rename(), solution, any, lines, props (+84 more)

### Community 93 - "environment"
Cohesion: 0.34
Nodes (20): environment, ALLOWED_EMAILS, DATABASE_URL, FASTEMBED_CACHE_PATH, GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET (+12 more)

### Community 94 - "Hybrid search (tsvector + pgvector RRF)"
Cohesion: 0.32
Nodes (8): Plan: Phase 4 RAG Ask + slides per subject, documents and chunks tables, Local fastembed multilingual embeddings, Hybrid search (tsvector + pgvector RRF), Spec: Phase 4b Ask as Chat over Decks, Deck Outline (automatic and AI), Per-page structure extraction (label, title, headings, footer), Term-weighted BM25-style Search with embedding blend

### Community 95 - "vite.config.ts"
Cohesion: 0.25
Nodes (6): vite@^8.0.8, vite-plugin-vue-devtools@^8.1.1, @vitejs/plugin-vue@^6.0.6, vite, vite-plugin-vue-devtools, @vitejs/plugin-vue

### Community 96 - "question_blocks"
Cohesion: 0.33
Nodes (10): question_blocks(), _task(), test_answer_blocks_stay_under_50(), test_answer_without_text_or_verdict_skips_empty_section(), test_fallback_text_survives_long_text(), test_header_cut_to_150(), test_long_text_and_many_options(), test_many_images_stay_under_50_blocks() (+2 more)

### Community 98 - "interactions"
Cohesion: 0.20
Nodes (10): commands(), events(), _form(), _handle(), interactions(), Global Constraints, Phase 5a: integrations + Slack Implementation Plan, Review Focus (+2 more)

### Community 99 - "test_rag_slides.py"
Cohesion: 0.04
Nodes (46): lookup(), LookupIn, search_hints(), search_subject(), SearchIn, Chunk, DeckPage, embed() (+38 more)

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

### Community 108 - "PdfDropZone.vue"
Cohesion: 0.38
Nodes (6): dragging, emit, input, onChange(), onDrop(), props

### Community 110 - "MaterialView.spec.ts"
Cohesion: 0.50
Nodes (4): docs, json(), open(), viewer

### Community 111 - "Exam-sim upgrade roadmap"
Cohesion: 0.33
Nodes (6): Postgres job queue (SKIP LOCKED) and worker, Inbound Slack webhook (planned), SSE job progress, Phase 5: agent, Slack/Notion, webhooks (planned), Pipeline repair agent (planned), Exam-sim upgrade roadmap

### Community 112 - "MCP server at /mcp"
Cohesion: 0.47
Nodes (5): Personal access tokens (hashed, Bearer), MCP server at /mcp, record_practice (practice = attempt), Use exam-sim from Claude (MCP), MCP tools (list_subjects, progress, find_tasks, get_task, my_history, record_practice, set_points)

### Community 113 - "Client grading library (planGrading, streamGrade)"
Cohesion: 0.33
Nodes (6): Attempt store LLM run/stop/rubric saving, Client grading library (planGrading, streamGrade), POST /api/grade route with RateLimiter, LlmCard and LlmSummary UI, POST /api/materials/lookup (where to read this), LLM card layout per subtask

### Community 116 - "Text-first grading inputs"
Cohesion: 0.50
Nodes (4): Docling enrichment (formulas as LaTeX), fold_scripts (sub/superscripts into text), Points extraction rules and mc_rule, Text-first grading inputs

### Community 117 - ".prettierrc.json"
Cohesion: 0.40
Nodes (4): printWidth, $schema, semi, singleQuote

### Community 119 - "docling enrichment (enrich.py)"
Cohesion: 0.50
Nodes (3): docling enrichment (enrich.py), fold_scripts sub/superscripts, visual() region rule

### Community 135 - "conftest.py"
Cohesion: 0.06
Nodes (31): _html(), collect(), main(), write_report(), available(), enrich(), extract(), process() (+23 more)

### Community 140 - "SubjectSelect.vue"
Cohesion: 0.18
Nodes (17): Task 4: Button and docs, commit(), emit, library, model, names, options, createSubject() (+9 more)

### Community 142 - "PdfDropZone.vue"
Cohesion: 0.40
Nodes (4): Decisions already made (don't revisit), Done, Not done, Phase 5a Slack: status and what's left

### Community 143 - "services"
Cohesion: 0.11
Nodes (17): internal, networks, backend, edge, tunnel, services, web, build (+9 more)

### Community 144 - "split"
Cohesion: 0.43
Nodes (3): split(), test_split_cuts_a_single_huge_line_and_skips_blanks(), test_split_packs_lines_and_respects_limit()

### Community 145 - "test_slack_events.py"
Cohesion: 0.40
Nodes (4): Anki export, Import, Not exported, What is in the deck

### Community 146 - "test_chats.py"
Cohesion: 0.22
Nodes (7): pin_first_slide(), test_ai_turn_errors(), test_ai_turn_holds_no_db_connection_while_the_llm_answers(), test_ai_turn_sends_only_pinned_pages_and_the_last_messages_and_cites_only_pins(), test_another_users_chat_is_404(), test_ask_preview_is_dev_only_and_calls_no_llm(), test_pins_are_saved_and_foreign_pages_dropped()

### Community 147 - "db"
Cohesion: 0.12
Nodes (17): cap_add, cap_drop, environment, healthcheck, image, networks, restart, security_opt (+9 more)

### Community 148 - "x-backend-env"
Cohesion: 0.12
Nodes (17): x-backend-env, ALLOWED_EMAILS, DATABASE_URL, FASTEMBED_CACHE_PATH, GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET (+9 more)

### Community 149 - "quiz.py"
Cohesion: 0.25
Nodes (12): _command(), _interact(), connect_message(), message(), answer(), _exam_url(), linked_user(), question() (+4 more)

### Community 153 - "api"
Cohesion: 0.15
Nodes (13): build, cap_drop, command, depends_on, image, networks, restart, security_opt (+5 more)

### Community 157 - "httpx"
Cohesion: 0.14
Nodes (10): disconnect(), load(), exchange(), exchange_notion(), notion_callback(), _save(), slack_callback(), revoke() (+2 more)

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
Cohesion: 0.29
Nodes (6): Flashcards in Notion, Manual check (open), Rules, Set up, What you get, Subject

### Community 168 - "Review Focus"
Cohesion: 0.33
Nodes (5): Global Constraints, Review Focus, Slack /quiz crops Implementation Plan, Task 3: Gate — one real question in Slack (manual, throwaway), Task 5: Self-check buttons

### Community 169 - "cloudflared"
Cohesion: 0.22
Nodes (9): cap_drop, command, environment, image, networks, restart, security_opt, TUNNEL_TOKEN (+1 more)

### Community 170 - "x-backend"
Cohesion: 0.29
Nodes (7): x-backend, build, cap_drop, image, restart, security_opt, volumes

### Community 171 - "features"
Cohesion: 0.53
Nodes (4): features(), summary(), test_issue_messages_are_grouped_by_kind(), test_select_covers_every_feature_with_few_pdfs()

### Community 179 - "test_numprog_integration"
Cohesion: 0.29
Nodes (5): test_numprog_integration(), Decisions already made, Done, Not done, Phase 5b-2 handoff: Notion export

## Knowledge Gaps
- **34 isolated node(s):** `exam-sim-backend`, `@vue/tsconfig/tsconfig.dom.json`, `./tsconfig.app.json`, `Eval metrics (exact, in_range, mae, calibration)`, `Where to read this lookup` (+29 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1286 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **18 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Subject` connect `Flashcards in Notion` to `SubjectSelect.vue`, `httpx`, `Documents Client API`?**
  _High betweenness centrality (0.258) - this node is a cross-community bridge._
- **Are the 59 inferred relationships involving `User` (e.g. with `lookup()` and `search_hints()`) actually correct?**
  _`User` has 59 INFERRED edges - model-reasoned connections that need verification._
- **What connects `exam-sim-backend`, `@vue/tsconfig/tsconfig.dom.json`, `./tsconfig.app.json` to the rest of the system?**
  _34 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `stores/attempt.ts` be split into smaller, more focused modules?**
  _Cohesion score 0.06976744186046512 - nodes in this community are weakly interconnected._
- **Why does `Exam` connect `Exam` to `Attempt`, `test_rag_slides.py`, `routes.py`, `test_slack_quiz.py`, `Flashcards in Notion`, `worker/main.py`, `select`, `test_sync.py`, `db/models.py`, `httpx`?**
  _High betweenness centrality (0.238) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `signed_in()` (e.g. with `fake_identity()` and `Task 3: Connect, list and disconnect Slack (OAuth)`) actually correct?**
  _`signed_in()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Should `Attempt` be split into smaller, more focused modules?**
  _Cohesion score 0.12299465240641712 - nodes in this community are weakly interconnected._