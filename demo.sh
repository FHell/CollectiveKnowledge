#!/usr/bin/env bash
# Debug/demo server: the full Knowledge Forge experience on localhost,
# with the auth workflow MOCKED — no Forgejo, no ORCID, no Docker.
#
#   ./demo.sh [SITE_PORT] [FORGE_PORT]      (defaults 8000, 8001)
#
# What you get:
#   http://127.0.0.1:<SITE_PORT>/   the published site (this repo IS the
#                                   demo book), seeded with a change
#                                   under review, a discussion and a
#                                   request-changes verdict
#   "Sign in with ORCID (demo)"     the real site→forge OAuth2+PKCE flow,
#                                   but the forge's ORCID step is a
#                                   persona picker (tests/stub_forge.py);
#                                   the persona's ORCID iD becomes your
#                                   username, as in production. Pasting a
#                                   persona iD as a token also works.
#   a mock CI loop                  new/updated changes get rendered diff
#                                   pages within ~3 s; merging a change
#                                   rebuilds the book — like the real
#                                   Forgejo Actions workflows.
#
# Everything lives in a temp directory and is torn down on Ctrl-C.
# Nothing talks to the network beyond 127.0.0.1.
set -euo pipefail

SITE_PORT=${1:-8000}
FORGE_PORT=${2:-8001}
ROOT=$(cd "$(dirname "$0")" && pwd)

command -v book >/dev/null || {
  echo "the 'book' CLI is not installed — run: pip install -e ." >&2; exit 1; }

WORK=$(mktemp -d)
PIDS=()
cleanup() { for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done; rm -rf "$WORK"; }
trap cleanup EXIT INT TERM

JOSIAH="0000-0002-1825-0097"   # Josiah Carberry — ORCID's fictional researcher
ADA="0000-0001-0000-0042"
GRACE="0000-0003-0000-0007"
API="http://127.0.0.1:$FORGE_PORT"

echo "==> Preparing demo repository (this repo is the demo book)"
git clone -q --bare "$ROOT" "$WORK/demo/book.git"
git -C "$WORK/demo/book.git" symbolic-ref HEAD refs/heads/main

# a change under review, authored by a persona
git clone -q "$WORK/demo/book.git" "$WORK/seed"
(
  cd "$WORK/seed"
  git config user.name "$JOSIAH"
  git config user.email "$JOSIAH@demo.example"
  git checkout -q -b "$JOSIAH/boundary-remark"
  cat >> chapters/02-heat-equation.md <<'EOF'

A remark on boundaries: the behaviour of solutions is dictated as much
by the boundary conditions as by the equation itself — insulated ends
conserve total heat, while fixed-temperature ends let it drain away.
EOF
  git commit -qam "add remark on the role of boundary conditions"
  git push -q origin "$JOSIAH/boundary-remark"
)

echo "==> Starting stub forge with mock ORCID sign-in on :$FORGE_PORT"
python3 "$ROOT/tests/stub_forge.py" "$FORGE_PORT" "$WORK/demo/book.git" demo book &
PIDS+=($!)
for _ in $(seq 50); do
  curl -fsS "$API/api/v1/repos/demo/book/_state" >/dev/null 2>&1 && break
  sleep 0.1
done

echo "==> Seeding a discussion on the change"
curl -fsS -X POST -H "Authorization: token $JOSIAH" -H "Content-Type: application/json" \
  -d '{"head": "'"$JOSIAH"'/boundary-remark", "base": "main",
       "title": "Add remark on boundary conditions",
       "body": "The chapter never says why boundary conditions matter; this adds one paragraph."}' \
  "$API/api/v1/repos/demo/book/pulls" >/dev/null
curl -fsS -X POST -H "Authorization: token $ADA" -H "Content-Type: application/json" \
  -d '{"body": "Nice addition — but should it distinguish Dirichlet from Neumann by name?"}' \
  "$API/api/v1/repos/demo/book/issues/1/comments" >/dev/null
curl -fsS -X POST -H "Authorization: token $GRACE" -H "Content-Type: application/json" \
  -d '{"event": "REQUEST_CHANGES", "body": "Please name the two condition types; students will meet the terms in the exercises."}' \
  "$API/api/v1/repos/demo/book/pulls/1/reviews" >/dev/null

echo "==> Building the site"
git clone -q "$WORK/demo/book.git" "$WORK/checkout"
python3 - "$WORK/checkout" "$API" <<'EOF'
import sys
from pathlib import Path
from book.config import write_local_config
d, api = sys.argv[1:]
write_local_config(Path(d), {"forgejo": {"url": api, "owner": "demo", "repo": "book"}})
EOF
cat >> "$WORK/checkout/book.toml" <<'EOF'

[oauth]
client_id = "demo"
label = "Sign in with ORCID (demo)"
EOF

SITE="$WORK/site"
build_book() {
  (cd "$WORK/checkout" && book build -o "$SITE/book" >/dev/null)
  for f in style.css forge-client.js web-actions.js forge.json; do
    cp "$SITE/book/$f" "$SITE/$f"
  done
  cp "$ROOT/site/landing.html" "$SITE/index.html"
}
build_book

# seed a paragraph discussion, anchored to a real content hash
python3 - "$WORK/checkout" "$API" "$ADA" <<'EOF'
import json, sys, urllib.request
from docutils import nodes
from book.mystdoc import para_hash, parse
root, api, ada = sys.argv[1:]
text = open(f"{root}/chapters/01-about.md").read()
para = next(parse(text).findall(nodes.paragraph)).astext()
h = para_hash(para)
body = json.dumps({
    "title": f"Discussion: chapters/01-about.md ¶{h}",
    "body": f"> {para[:120]}\n\nShould this opening also mention that reading needs no account?"
            f"\n\n---\nParagraph `{h}` in `chapters/01-about.md` — opened from the published book.",
}).encode()
req = urllib.request.Request(f"{api}/api/v1/repos/demo/book/issues", data=body,
    headers={"Authorization": f"token {ada}", "Content-Type": "application/json"})
urllib.request.urlopen(req)
EOF

# --- mock CI: rendered diffs for open changes, rebuild on merge ---------------
render_diffs() {
  git -C "$WORK/checkout" fetch -q origin \
    "+refs/heads/main:refs/remotes/origin/main" \
    "+refs/pull/*/head:refs/remotes/origin/pull/*" 2>/dev/null || return 0
  local main_sha
  main_sha=$(git -C "$WORK/checkout" rev-parse origin/main)
  if [ "$main_sha" != "$(cat "$WORK/.main-sha" 2>/dev/null || true)" ]; then
    git -C "$WORK/checkout" merge -q --ff-only origin/main 2>/dev/null || true
    build_book
    echo "$main_sha" > "$WORK/.main-sha"
  fi
  local prs n sha
  prs=$(curl -fsS "$API/api/v1/repos/demo/book/pulls?state=open" 2>/dev/null \
    | python3 -c "import json,sys; print(' '.join(str(p['number']) for p in json.load(sys.stdin)))") || return 0
  for n in $prs; do
    sha=$(git -C "$WORK/checkout" rev-parse -q --verify "refs/remotes/origin/pull/$n" 2>/dev/null) || continue
    [ "$sha" = "$(cat "$WORK/.pr-$n.sha" 2>/dev/null || true)" ] && continue
    mkdir -p "$SITE/diffs/pr-$n"
    (cd "$WORK/checkout" && python3 - "$n" "$SITE/diffs/pr-$n/index.html" <<'EOF'
import sys
from book.diff import render_diff
n, out = int(sys.argv[1]), sys.argv[2]
render_diff(".", "HEAD", f"refs/remotes/origin/pull/{n}", out_path=out,
            title=f"Change #{n} vs main", web_actions={"base": "../../", "pr": n})
EOF
    ) && echo "$sha" > "$WORK/.pr-$n.sha"
  done
}
render_diffs

ci_loop() { while true; do sleep 3; render_diffs; done; }
ci_loop &
PIDS+=($!)

python3 -m http.server "$SITE_PORT" --bind 127.0.0.1 -d "$SITE" >/dev/null 2>&1 &
PIDS+=($!)

cat <<EOF

  Knowledge Forge demo is up (Ctrl-C stops everything):

    site        http://127.0.0.1:$SITE_PORT/
    diff page   http://127.0.0.1:$SITE_PORT/diffs/pr-1/   (seeded change + discussion)
    stub forge  $API

  Sign in via the button (mock ORCID persona picker), or paste a
  persona iD as a token:

    $JOSIAH   Josiah Carberry (change author)
    $ADA   Ada Demo
    $GRACE   Grace Example

  Try: reply on the diff page, request changes, merge (the book at
  /book/ rebuilds in ~3 s), tap a paragraph in chapter 1 to find Ada's
  discussion, edit a paragraph to open a new change (its diff page
  appears within ~3 s), vouch for one.

EOF

wait
