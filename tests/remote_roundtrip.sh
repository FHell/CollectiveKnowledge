#!/usr/bin/env bash
# Phase 2 acceptance: full student/instructor round trip against a stub
# Forgejo API (tests/stub_forge.py) backed by a real bare git repo.
#
#   student:    clone → change new → save → submit          (PR #1 appears)
#   instructor: changes → review 1 (rendered diff) → edit → push-review 1
#               → request-changes 1 → approve 1 --vouch
#   asserts:    main has student + instructor commits, merge commit,
#               vouches.yaml updated, blame attributes the student.
set -euo pipefail

fail() { echo "ROUNDTRIP FAIL: $*" >&2; exit 1; }

HERE=$(cd "$(dirname "$0")" && pwd)
WORK=$(mktemp -d)
PORT=$(python3 -c "import socket; s=socket.socket(); s.bind(('127.0.0.1',0)); print(s.getsockname()[1]); s.close()")
STUB_PID=""
trap '[ -n "$STUB_PID" ] && kill "$STUB_PID" 2>/dev/null; rm -rf "$WORK"' EXIT
cd "$WORK"

export GIT_AUTHOR_NAME="Setup" GIT_COMMITTER_NAME="Setup"
export GIT_AUTHOR_EMAIL="setup@example.org" GIT_COMMITTER_EMAIL="setup@example.org"

# --- canonical repo + bare origin -------------------------------------------
mkdir seed && (cd seed && book init . --title "Course Notes" >/dev/null)
git clone --bare -q seed "$WORK/class/notes.git"
git -C "$WORK/class/notes.git" symbolic-ref HEAD refs/heads/main
# from here on, identities come from per-repo git config, not the environment
unset GIT_AUTHOR_NAME GIT_COMMITTER_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_EMAIL

# --- stub forge --------------------------------------------------------------
python3 "$HERE/stub_forge.py" "$PORT" "$WORK/class/notes.git" class notes &
STUB_PID=$!
for _ in $(seq 50); do
  curl -fsS "http://127.0.0.1:$PORT/api/v1/repos/class/notes/_state" >/dev/null 2>&1 && break
  sleep 0.1
done
API="http://127.0.0.1:$PORT"

configure() { # dir user
  python3 - "$1" "$2" "$API" <<'EOF'
import sys
from pathlib import Path
from book.config import write_local_config
d, user, api = sys.argv[1:]
write_local_config(Path(d), {
    "user": {"name": user},
    "forgejo": {"url": api, "owner": "class", "repo": "notes"},
})
EOF
  git -C "$1" config user.name "$2"
  git -C "$1" config user.email "$2@example.org"
}

# --- student: submit a change -------------------------------------------------
book clone "file://$WORK/class/notes.git" student --user alice >/dev/null
configure student alice
(
  cd student
  book change new "add example" >/dev/null
  python3 - <<'EOF'
p = "chapters/01-introduction.md"
t = open(p).read().replace("e^{i\\pi} + 1 = 0", "e^{i\\pi} = -1")
t += "\nAlice adds: the identity follows from $\\cos\\pi = -1$.\n"
open(p, "w").write(t)
EOF
  book save -m "add example about Euler's identity" >/dev/null
  book submit >/dev/null
  book submit >/dev/null   # idempotency: second submit must not create PR #2
)
PR_COUNT=$(curl -fsS "$API/api/v1/repos/class/notes/pulls?state=open" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))")
[ "$PR_COUNT" = "1" ] && echo "ok: submit idempotent (1 open PR)" || fail "expected 1 open PR, got $PR_COUNT"

# --- instructor: list, review, edit, push back, approve+vouch ------------------
book clone "file://$WORK/class/notes.git" instructor --user frank >/dev/null
configure instructor frank
(
  cd instructor
  book changes | grep -q "alice" || fail "book changes does not list alice's PR"
  book review 1 --no-open >/dev/null
  git rev-parse --abbrev-ref HEAD | grep -q "review/pr-1" || fail "review did not check out review/pr-1"
  grep -q "<ins" _build/diff-pr-1.html || fail "review diff missing <ins>"

  # instructor edits the student's change directly
  python3 - <<'EOF'
p = "chapters/01-introduction.md"
t = open(p).read().replace("Alice adds:", "Alice notes:")
open(p, "w").write(t)
EOF
  book save -m "wording tweak" >/dev/null
  book push-review 1 >/dev/null
  book request-changes 1 -m "please double-check the sign" >/dev/null
  book approve 1 --vouch --note "checked derivation" >/dev/null
)

# --- assertions on the merged result ------------------------------------------
git clone -q "file://$WORK/class/notes.git" final
cd final
git log --pretty=%s | grep -q "Merge pull request #1" || fail "no merge commit on main"
git log --pretty="%an %s" | grep -q "alice add example" || fail "student commit lost"
git log --pretty="%an %s" | grep -q "frank wording tweak" || fail "instructor edit lost"
grep -q "Alice notes:" chapters/01-introduction.md || fail "instructor edit not in merged content"
grep -q "frank" meta/vouches.yaml || fail "vouch by frank missing"
grep -q "checked derivation" meta/vouches.yaml || fail "vouch note missing"
book blame chapters/01-introduction.md | grep -q "alice" || fail "blame does not attribute alice"

STATE=$(curl -fsS "$API/api/v1/repos/class/notes/_state")
echo "$STATE" | grep -q "REQUEST_CHANGES" || fail "request-changes review not recorded"
echo "$STATE" | python3 -c "
import json, sys
s = json.load(sys.stdin)
assert s['prs']['1']['state'] == 'closed' and s['prs']['1']['merged'], 'PR not merged'
" || fail "PR state wrong after approve"

echo "ROUNDTRIP OK"
