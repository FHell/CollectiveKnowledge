#!/usr/bin/env bash
# Build the static web-workflow demo (published to GitHub Pages by
# .github/workflows/pages.yml, but runnable locally too):
#
#   <out>/index.html        landing page explaining the demo
#   <out>/book/             the published book, as deployed after merges
#                           (click any paragraph: authorship + vouches)
#   <out>/diffs/pr-1/       the rendered AST diff for a pending change —
#                           the page CI links on every PR
#
# A throwaway demo book is created in a temp dir with two authors
# (Frank the instructor, Alice a student), instructor vouches, one merged
# student change, and one *pending* change whose diff is rendered.
set -euo pipefail

OUT=$(mkdir -p "${1:-public}" && cd "${1:-public}" && pwd)
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

as_frank() {
  GIT_AUTHOR_NAME="Frank (instructor)" GIT_AUTHOR_EMAIL="frank@example.org" \
  GIT_COMMITTER_NAME="Frank (instructor)" GIT_COMMITTER_EMAIL="frank@example.org" "$@"
}
as_alice() {
  GIT_AUTHOR_NAME="Alice (student)" GIT_AUTHOR_EMAIL="alice@example.org" \
  GIT_COMMITTER_NAME="Alice (student)" GIT_COMMITTER_EMAIL="alice@example.org" "$@"
}

cd "$WORK"
as_frank book init . --title "Collective Knowledge — Demo Book" >/dev/null

# --- instructor writes the initial content ----------------------------------
cat > chapters/01-introduction.md <<'EOF'
# Introduction

This is a demo of the collaborative document engine. Every paragraph you
see is *clickable*: click one to see who wrote it and who vouches for it.

Students propose changes from the command line with `book submit`; each
change becomes a pull request, and a rendered diff page (like the one
linked from the demo landing page) is attached to it automatically.

The instructor reviews, edits if needed, and merges. Merged text lands
here, with authorship preserved paragraph by paragraph.
EOF

cat > chapters/02-heat-equation.md <<'EOF'
# The heat equation

The temperature $u(x, t)$ of a thin rod evolves according to the heat
equation, $u_t = \alpha\, u_{xx}$, where $\alpha$ is the thermal
diffusivity of the material.

Separation of variables with $u(x,t) = X(x)\,T(t)$ splits the problem
into two ordinary differential equations coupled by a constant
$-\lambda$.

For a rod of length $L$ with ends held at zero temperature, the general
solution is the Fourier sine series
$u(x,t) = \sum_{n=1}^{\infty} b_n \sin\!\left(\frac{n\pi x}{L}\right) e^{-\alpha (n\pi/L)^2 t}.$
EOF

cat > _toc.yml <<'EOF'
format: book
chapters:
  - file: chapters/01-introduction.md
  - file: chapters/02-heat-equation.md
EOF

as_frank git add -A
as_frank git commit -qm "write introduction and heat equation chapter"
as_frank book vouch chapters/02-heat-equation.md --note "derivation checked" >/dev/null

# --- a student change, already reviewed and merged --------------------------
as_alice git checkout -qb alice/boundary-remark
cat >> chapters/02-heat-equation.md <<'EOF'

Physically, the exponential factor says that high spatial frequencies
decay fastest: fine temperature details are smoothed out almost
immediately, while the slowest mode $n = 1$ dominates the long-time
behaviour.
EOF
as_alice git commit -qam "add physical interpretation of the decay factor"
as_alice git checkout -q main
as_frank git merge -q --no-ff alice/boundary-remark \
  -m "Merge pull request #1: add physical interpretation of the decay factor"
as_frank book vouch chapters/02-heat-equation.md --note "nice addition, verified" >/dev/null

# --- the published book (what deploy.yml puts at / after each merge) --------
book build >/dev/null
mkdir -p "$OUT/book"
cp -r _build/html/. "$OUT/book/"

# --- a pending change, awaiting review: its rendered diff -------------------
as_alice git checkout -qb alice/fix-diffusivity
python3 - <<'EOF'
p = "chapters/02-heat-equation.md"
t = open(p).read()
t = t.replace(
    "the heat\nequation, $u_t = \\alpha\\, u_{xx}$",
    "the heat\nequation, $u_t = \\kappa\\, u_{xx}$",
)
t = t.replace(
    "where $\\alpha$ is the thermal\ndiffusivity of the material.",
    "where $\\kappa$ is the thermal\ndiffusivity of the material "
    "(the symbol $\\kappa$ is standard in the literature).",
)
t = t.replace("e^{-\\alpha (n\\pi/L)^2 t}", "e^{-\\kappa (n\\pi/L)^2 t}")
open(p, "w").write(t)
EOF
as_alice git commit -qam "use standard symbol kappa for thermal diffusivity"

mkdir -p "$OUT/diffs/pr-2"
python3 - "$OUT/diffs/pr-2/index.html" <<'EOF'
import sys
from book.diff import render_diff
render_diff(
    ".", "main", "alice/fix-diffusivity",
    out_path=sys.argv[1],
    title="Change #2 by alice: use standard symbol κ for thermal diffusivity",
)
EOF

# --- landing page ------------------------------------------------------------
cp "$HERE/landing.html" "$OUT/index.html"

echo "Demo site written to $OUT"
