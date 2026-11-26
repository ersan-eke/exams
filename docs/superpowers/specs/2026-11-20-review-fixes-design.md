# Review fixes (14 findings) — design

Small change, one batch. Each finding is independent; the user listed them with fix and reason, so those are taken as given.

## Intent
Close the 14 findings of the last review: two must-fix (anonymous upload can fill the disk; a Deck deleted mid-job kills the worker), four should-fix, eight nice-to-have.

## Non-goals
No new features, no change to the pipeline, no `/api/sync` redesign beyond paging attempts.

## Approaches
Only one sensible way: fix each at the layer that owns it (see the plan). One real alternative, for sync paging: keep `since` as the only cursor and cap pages by count. Rejected: the 10 s overlap on `since` makes a page of more than `limit` rows inside the overlap never advance, and a `now()` cursor would skip the rest of a cut-off page. So paging uses a keyset `(updated_at, id)`.

## Decisions
- User: all 14 fixed as described; exam upload cap about 50 MB (no real exam PDF over 50 MB was confirmed, so it is 50 MB and a constant).
- My calls (flag when reviewing):
  - Shared `save_capped` helper in `core/storage.py` used by both upload routes.
  - Sync paging: attempts only, 50 per page, new query param `after` (attempt id) and response fields `after` and `more`; exams are sent on the first page only; overlap applies to the first page only; the client keeps the first page's cursor.
  - Job event stream past its deadline (15 min, the worker's STALE time) sends one final `failed`/`server` event instead of just closing, because a closed `EventSource` reconnects by itself.
  - Rate limiter sweeps empty clients at most once per window.
  - Deck is deleted on failure only for `unreadable` and `scanned`.
