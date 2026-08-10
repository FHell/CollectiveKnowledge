#!/usr/bin/env bash
# Phase 0 regression guard: local workflow end-to-end.
# Creates a temp repo, inits a book, builds, makes a change branch, edits,
# and asserts the rendered diff contains <ins>/<del> markup.
set -euo pipefail

fail() { echo "SMOKE FAIL: $*" >&2; exit 1; }

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

export GIT_AUTHOR_NAME="Smoke Tester" GIT_COMMITTER_NAME="Smoke Tester"
export GIT_AUTHOR_EMAIL="smoke@example.org" GIT_COMMITTER_EMAIL="smoke@example.org"
git config --global user.name  >/dev/null 2>&1 || git config --global user.name "Smoke Tester"
git config --global user.email >/dev/null 2>&1 || git config --global user.email "smoke@example.org"

# --- init + build -----------------------------------------------------------
book init . --title "Smoke Book" >/dev/null
[ -f book.toml ] && [ -f _toc.yml ] && [ -f meta/vouches.yaml ] || fail "init scaffold incomplete"

cat > chapters/02-formulas.md <<'EOF'
# Formulas

The energy identity is $E = mc^2$ as everyone knows.

A second paragraph that will stay unchanged.
EOF
git add -A && git commit -qm "add formulas chapter"

book build >/dev/null
[ -f _build/html/index.html ] || fail "build produced no index.html"
[ -f _build/html/02-formulas.html ] || fail "build produced no chapter page"
grep -q "data-phash" _build/html/02-formulas.html || fail "paragraph hashes missing from HTML"
grep -q '"byHash"' _build/html/blame.json || fail "blame.json missing/empty"
grep -Eq 'src="overlay.js"' _build/html/02-formulas.html || fail "overlay.js not referenced relatively"
grep -q 'href="style.css"' _build/html/02-formulas.html || fail "style.css not referenced relatively"
if grep -E 'href="/|src="/' _build/html/02-formulas.html | grep -v 'https://'; then
  fail "absolute asset paths found (site must work under a URL prefix)"
fi

# --- blame + vouch ----------------------------------------------------------
book blame chapters/02-formulas.md | grep -q "Smoke Tester" || fail "blame does not attribute author"
book vouch chapters/02-formulas.md --note "smoke" >/dev/null
grep -q "smoke" meta/vouches.yaml || fail "vouch not recorded"
git log -1 --pretty=%s | grep -q "vouch" || fail "vouch not committed"

# --- change branch + rendered diff ------------------------------------------
book change new "tweak formula" >/dev/null
git rev-parse --abbrev-ref HEAD | grep -q "/tweak-formula" || fail "change branch not namespaced"

python3 - <<'EOF'
p = "chapters/02-formulas.md"
t = open(p).read()
t = t.replace("E = mc^2", "E = mc^3")
t = t.replace("as everyone knows", "as every physicist knows")
open(p, "w").write(t)
EOF
book save -m "tweak" >/dev/null

book diff main --render -o "$WORK/diff.html" >/dev/null
[ -f "$WORK/diff.html" ] || fail "rendered diff not written"
grep -q "<ins" "$WORK/diff.html" || fail "rendered diff missing <ins>"
grep -q "<del" "$WORK/diff.html" || fail "rendered diff missing <del>"
grep -q 'class="math"' "$WORK/diff.html" || fail "rendered diff lost math markup"

# render_diff must be callable as a function (CI entry point)
python3 - "$WORK" <<'EOF'
import sys
from pathlib import Path
from book.diff import render_diff
out = render_diff(Path.cwd(), "main", None, out_path=Path(sys.argv[1]) / "diff2.html")
html = out.read_text()
assert "<ins" in html and "<del" in html, "programmatic render_diff broken"
EOF

# frontmatter-only changes must NOT show up as content changes
git checkout -q main
python3 - <<'EOF'
p = "chapters/02-formulas.md"
t = open(p).read()
open(p, "w").write("---\ntitle: overridden\n---\n" + t)
EOF
book diff main | grep -q "No content changes" || fail "frontmatter-only diff not skipped"
git checkout -q -- .

echo "SMOKE OK"
