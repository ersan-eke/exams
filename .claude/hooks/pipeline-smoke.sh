#!/bin/sh
# PostToolUse: after an edit under backend/app/pipeline/, run the pipeline regression check.
# Exit 2 sends the diff back to Claude; no samples/ (fresh clone) means nothing to check.
f=$(jq -r '.tool_input.file_path // .tool_response.filePath // empty')
case "$f" in */backend/app/pipeline/*.py) ;; *) exit 0 ;; esac
root="$CLAUDE_PROJECT_DIR"
[ -d "$root/samples" ] || exit 0
out=$(cd "$root/backend" && uv run python -m app.pipeline.smoke 2>/dev/null) && exit 0
printf 'Pipeline smoke check changed (accept with `uv run python -m app.pipeline.smoke --update` if intended):\n%s\n' "$out" >&2
exit 2
