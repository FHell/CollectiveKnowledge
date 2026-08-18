#!/usr/bin/env bash
# Browser acceptance: discussions on proposed edits work on the published
# site. Builds the site against a stub forge, renders the diff page for a
# real change, then drives a headless Chromium through reading the
# thread, signing in, replying, and requesting changes
# (tests/web_discussion_test.py).
#
# Requires: pip install playwright, plus a Chromium — either playwright's
# own or a system one via BOOK_E2E_CHROMIUM (default /opt/pw-browsers/chromium).
set -euo pipefail

fail() { echo "WEB E2E FAIL: $*" >&2; exit 1; }

python3 -c "import playwright" 2>/dev/null || fail "playwright not installed (pip install playwright)"

HERE=$(cd "$(dirname "$0")" && pwd)
WORK=$(mktemp -d)
API_PORT=$(python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1]); s.close()")
SITE_PORT=$(python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1]); s.close()")
PIDS=()
trap 'for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done; rm -rf "$WORK"' EXIT
cd "$WORK"

export GIT_AUTHOR_NAME="Setup" GIT_COMMITTER_NAME="Setup"
export GIT_AUTHOR_EMAIL="setup@example.org" GIT_COMMITTER_EMAIL="setup@example.org"

# --- canonical repo + a change branch to discuss ---------------------------------
mkdir seed && (cd seed && book init . --title "Course Notes" >/dev/null)
git clone --bare -q seed "$WORK/class/notes.git"
git -C "$WORK/class/notes.git" symbolic-ref HEAD refs/heads/main

git clone -q "file://$WORK/class/notes.git" alice
(
  cd alice
  git config user.name alice && git config user.email alice@example.org
  git checkout -q -b alice/clarify-euler
  python3 - <<'EOF'
p = "chapters/01-introduction.md"
t = open(p).read() + "\nAlice adds: step 2 rearranges the identity.\n"
open(p, "w").write(t)
EOF
  git commit -qam "clarify Euler identity"
  git push -q origin alice/clarify-euler
)

# --- stub forge + change #1 + an existing comment by bob ---------------------------
python3 "$HERE/stub_forge.py" "$API_PORT" "$WORK/class/notes.git" class notes &
PIDS+=($!)
API="http://127.0.0.1:$API_PORT"
for _ in $(seq 50); do
  curl -fsS "$API/api/v1/repos/class/notes/_state" >/dev/null 2>&1 && break
  sleep 0.1
done

curl -fsS -X POST -H "Authorization: token alice" -H "Content-Type: application/json" \
  -d '{"head": "alice/clarify-euler", "base": "main", "title": "Clarify the Euler identity", "body": "Adds the missing rearrangement step."}' \
  "$API/api/v1/repos/class/notes/pulls" >/dev/null
curl -fsS -X POST -H "Authorization: token bob" -H "Content-Type: application/json" \
  -d '{"body": "Step 2 looks wrong to me — the sign should flip."}' \
  "$API/api/v1/repos/class/notes/issues/1/comments" >/dev/null

# --- build the site against the stub forge ---------------------------------------
git clone -q "file://$WORK/class/notes.git" checkout
python3 - <<EOF
from pathlib import Path
from book.config import write_local_config
write_local_config(Path("checkout"), {
    "forgejo": {"url": "$API", "owner": "class", "repo": "notes"},
})
EOF
(
  cd checkout
  book build -o "$WORK/site/book" >/dev/null
  for f in style.css forge-client.js web-actions.js forge.json; do
    cp "$WORK/site/book/$f" "$WORK/site/$f"
  done
  [ -f "$WORK/site/forge.json" ] || fail "book build wrote no forge.json"

  # rendered diff page for change #1, exactly as CI produces it
  git fetch -q origin "+refs/pull/1/head:refs/remotes/origin/pr-1"
  mkdir -p "$WORK/site/diffs/pr-1"
  python3 - <<'EOF'
from book.diff import render_diff
render_diff(
    ".", "HEAD", "refs/remotes/origin/pr-1",
    out_path="../site/diffs/pr-1/index.html",
    title="Change #1 vs main",
    web_actions={"base": "../../", "pr": 1},
)
EOF
)

# --- serve + drive the browser -----------------------------------------------------
python3 -m http.server "$SITE_PORT" --bind 127.0.0.1 -d "$WORK/site" >/dev/null 2>&1 &
PIDS+=($!)
sleep 0.3

SITE_URL="http://127.0.0.1:$SITE_PORT" API_URL="$API" \
  python3 "$HERE/web_discussion_test.py" || fail "browser assertions failed"

echo "WEB E2E OK"
