#!/usr/bin/env bash
# Assemble the public site (deployed by .forgejo/workflows/deploy.yml,
# runnable locally too):
#
#   <out>/index.html      landing page (live open-changes list, sign-in)
#   <out>/book/           the published book, built from THIS repository —
#                         the repo is the book; paragraphs are clickable
#                         and, signed in, can be discussed/vouched/edited
#   <out>/diffs/pr-N/     rendered AST diff + review bar + discussion
#                         thread for every OPEN pull request (list comes
#                         from the forge API when GITHUB_TOKEN /
#                         GITHUB_REPOSITORY / GITHUB_SERVER_URL are set —
#                         Forgejo Actions provides all three; skipped
#                         otherwise)
#
# Always builds the book from the CURRENT checkout, which the workflow
# pins to main — PR content is only ever read as data via `git show`,
# never executed.
set -euo pipefail

OUT=$(mkdir -p "${1:-public}" && cd "${1:-public}" && pwd)
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)
cd "$ROOT"

# --- the book -----------------------------------------------------------------
book build -o "$OUT/book"

# site-root copies of the shared assets + forge config, used by the
# landing page and the diff pages (they reference ../../ from diffs/pr-N/)
for f in style.css forge-client.js web-actions.js forge.json; do
  [ -f "$OUT/book/$f" ] && cp "$OUT/book/$f" "$OUT/$f"
done
cp "$HERE/landing.html" "$OUT/index.html"

# --- rendered diff + review bar + thread for every open PR ------------------------
if [ -n "${GITHUB_TOKEN:-}" ] && [ -n "${GITHUB_REPOSITORY:-}" ] && [ -n "${GITHUB_SERVER_URL:-}" ]; then
  PRS=$(curl -fsS -H "Authorization: token $GITHUB_TOKEN" \
    "${GITHUB_SERVER_URL%/}/api/v1/repos/$GITHUB_REPOSITORY/pulls?state=open&limit=50" \
    | python3 -c "import json,sys; print(' '.join(str(p['number']) for p in json.load(sys.stdin)))")
  echo "open changes: ${PRS:-none}"
  for N in $PRS; do
    git fetch -q origin "+refs/pull/$N/head:refs/remotes/origin/pr-$N" || {
      echo "warn: could not fetch PR #$N head, skipping"; continue; }
    mkdir -p "$OUT/diffs/pr-$N"
    python3 - "$N" "$OUT/diffs/pr-$N/index.html" <<'EOF'
import sys
from book.diff import render_diff
n, out = int(sys.argv[1]), sys.argv[2]
render_diff(
    ".", "HEAD", f"refs/remotes/origin/pr-{n}",
    out_path=out,
    title=f"Change #{n} vs main",
    web_actions={"base": "../../", "pr": n},
)
EOF
  done
else
  echo "no forge API env (GITHUB_TOKEN/GITHUB_REPOSITORY/GITHUB_SERVER_URL): skipping per-PR diff pages"
fi

echo "Site written to $OUT"
