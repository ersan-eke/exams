#!/usr/bin/env bash
# Publish a snapshot of this repo's main to the public repo, without history.
#
#   scripts/publish-public.sh                 dry run: mirror, stage, check, report, then undo
#   scripts/publish-public.sh --push "msg"    same checks, then commit and push
#
# PUBLIC_REPO = path of the public clone (default ../exam-sim-public).
# PUBLISH_DENY = file of extended regexes that must never appear in published lines (default .publish-deny,
# git-ignored: it holds the very names it guards against, so it must not be published itself).
# ALLOW_BINARY=1 lets changed binary files through after you looked at them.
set -euo pipefail

PRIV=$(git rev-parse --show-toplevel)
PUB=$(cd "${PUBLIC_REPO:-$PRIV/../exam-sim-public}" && pwd)
DENY=${PUBLISH_DENY:-$PRIV/.publish-deny}
PUSH=0
if [ "${1:-}" = "--push" ]; then PUSH=1; shift; fi
MSG=${1:-"Snapshot of private main $(git -C "$PRIV" rev-parse --short main)"}
# Each literal is split by a bracket ([-], [_], [/]) so this line does not match itself when the script is published.
SECRETS='sk-ant[-]|AIza[0-9A-Za-z_-]{20}|xox[abp]-[0-9]|ghp_[0-9A-Za-z]{20}|github_pat[_]|BEGIN [A-Z ]*PRIVATE KEY|/Users[/]|/home/[a-z]'
BAD_PATHS='\.(pdf|png|jpe?g|jsonl|apkg)$|(^|/)\.env(\..*)?$|(^|/)private/|^samples/|^results/'

die() { echo "publish: $*" >&2; exit 1; }
pub() { git -C "$PUB" "$@"; }

# Preconditions: published content is exactly what private origin/main already has.
[ -s "$DENY" ] || die "missing $DENY (one regex per line: your name, real exam file stems, email)"
grep -q '^$' "$DENY" && die "$DENY has an empty line (it would match everything)"
git -C "$PRIV" fetch -q origin
[ "$(git -C "$PRIV" rev-parse main)" = "$(git -C "$PRIV" rev-parse origin/main)" ] ||
  die "private main and origin/main differ: push (or pull) private main first"
[ "$(pub branch --show-current)" = main ] || die "$PUB is not on main"
[ -z "$(pub status --porcelain)" ] || die "$PUB has uncommitted changes"
pub fetch -q origin
pub merge -q --ff-only origin/main

# Mirror: delete every tracked file, extract private main, stage. Deleted files go away, new ones appear.
pub ls-files -z | (cd "$PUB" && xargs -0 rm -f)
git -C "$PRIV" archive main | tar -x -C "$PUB"
pub add -A
undo() { pub reset -q --hard && pub clean -fdq; }

if pub diff --cached --quiet; then undo; echo "publish: nothing to publish"; exit 0; fi

# Checks. Any failure undoes the mirror and stops.
fail() { echo "publish: $*" >&2; undo; exit 1; }
[ "$(pub write-tree)" = "$(git -C "$PRIV" rev-parse 'main^{tree}')" ] ||
  fail "staged tree differs from private main (a file ignored by .gitignore or export-ignore?)"
bad=$(pub diff --cached --name-only --diff-filter=AMR | grep -i -E "$BAD_PATHS" || true)
[ -z "$bad" ] || fail "exam, crop or env files staged:"$'\n'"$bad"
bin=$(pub diff --cached --numstat --diff-filter=AMR | awk -F'\t' '$1=="-"{print $3}')
[ -z "$bin" ] || [ "${ALLOW_BINARY:-}" = 1 ] || fail "binary files changed (check them, then ALLOW_BINARY=1):"$'\n'"$bin"
hits=$(pub diff --cached -U0 | grep -E '^\+([^+]|$)' | grep -o -i -E -f "$DENY" -e "$SECRETS" | sort | uniq -c || true)
[ -z "$hits" ] || fail "added lines match private or secret patterns:"$'\n'"$hits"

pub diff --cached --stat | tail -25
echo "publish: checks passed ($(pub diff --cached --name-only | wc -l | tr -d ' ') files)"

if [ "$PUSH" = 0 ]; then
  undo
  echo "publish: dry run, nothing committed. Review the stat above, then rerun with --push \"message\"."
  exit 0
fi
pub commit -q -m "$MSG"
pub push -q origin main
[ "$(pub rev-parse main)" = "$(pub rev-parse origin/main)" ] || die "push did not land"
echo "publish: pushed $(pub rev-parse --short main) to $(pub remote get-url origin)"
