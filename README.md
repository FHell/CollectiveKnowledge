# CollectiveKnowledge

A collaborative document engine for course books: students push text, the
instructor reviews rendered diffs, edits, approves and vouches — via a
local CLI workflow or entirely in the browser.

**Key principle:** metadata lives in git (vouches are committed to
`meta/`), the forge stays unmodified, and the `book` CLI is a thin layer
over git + the Forgejo REST API.

## The pieces

| Path | What it is |
|---|---|
| `book/` | the `book` CLI (`pip install .`) — init, build, blame, diff, vouch, change, save, clone, submit, changes, review, approve |
| `.forgejo/workflows/` | CI: rendered AST-diff per PR + site deploy on merge |
| `infra/` | docker-compose (Forgejo + Actions runner + nginx), bootstrap script |
| `tests/` | `smoke.sh` (local workflow) and `remote_roundtrip.sh` (full student/instructor round trip against a stub Forgejo API) |
| `STUDENT_GUIDE.md` | one page: from nothing to a submitted change |
| `INSTRUCTOR_GUIDE.md` | reviewing from the CLI or the browser |
| `MVP_BUILD_PLAN.md` | the plan this implements |

## Live demo (GitHub Pages)

The two static web artifacts — the published book (clickable paragraph
blame + vouches) and a rendered AST diff for a pending change — are
deployed to GitHub Pages by `.github/workflows/pages.yml`:
**https://fhell.github.io/CollectiveKnowledge/** (built from `demo/`).

## Quick start (local, no server)

```sh
pip install .
mkdir mybook && cd mybook
book init . --title "My Book"
book build                 # static site in _build/html/
book change new "first-edit"
# … edit chapters/ …
book save
book diff main --render --open
```

## Quick start (course deployment)

See `infra/README.md`: `docker compose up -d`, run `bootstrap.sh`, push
this repo, register the runner. Students follow `STUDENT_GUIDE.md`.

## Tests

```sh
pip install -e .
tests/smoke.sh              # local workflow regression guard
tests/remote_roundtrip.sh   # remote workflow against a stub forge
```
