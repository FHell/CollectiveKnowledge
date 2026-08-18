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
| `chapters/`, `meta/` | the book itself: content + committed vouch records |
| `book/` | the `book` CLI (`pip install .`) — init, build, blame, diff, vouch, change, save, clone, submit, changes, review, approve; works against GitHub and Forgejo/Gitea remotes |
| `book/assets/` | site runtime: overlay (blame/vouch popups), `forge-client.js` + `web-actions.js` (browser client for the forge API) |
| `site/` | landing page + site assembly script used by the Pages workflow |
| `.github/workflows/pages.yml` | builds book + per-open-PR rendered diffs, deploys to Pages |
| `.forgejo/workflows/` | CI for the self-hosted Forgejo variant |
| `infra/` | docker-compose (Forgejo + Actions runner + nginx), bootstrap script — optional, only for self-hosting |
| `tests/` | `smoke.sh` (local workflow) and `remote_roundtrip.sh` (full student/instructor round trip against a stub Forgejo API) |
| `STUDENT_GUIDE.md` | one page: from nothing to a submitted change |
| `INSTRUCTOR_GUIDE.md` | reviewing from the CLI or the browser |
| `MVP_BUILD_PLAN.md` | the plan this implements |
| `KNOWLEDGE_FORGE_ROADMAP.md` | the road ahead: phased plan to a feature-complete Knowledge Forge (fork-based editing for everyone, in-place discussion, validation roles & staleness, offline-first CLI) |

## The live book (GitHub Pages)

**This repository is a book**: `chapters/` at the root are the content,
and **https://fhell.github.io/CollectiveKnowledge/** is the published
site, rebuilt by `.github/workflows/pages.yml` on every merge and on
every change to an open PR.

The site is static, but fully interactive with no server of our own:
the browser talks directly to the GitHub API (CORS-open) with a
user-supplied fine-grained token stored in `localStorage`. Tap a
paragraph to see blame + vouches and to **discuss** (opens an issue
keyed to the paragraph's content hash), **vouch** (commits to
`meta/vouches.yaml`, or opens a PR when `main` is protected for you),
or **edit** (branch + commit + PR via the contents API). Rendered diff
pages for open changes carry a review bar (approve / request changes /
merge — always a merge commit). Git remains the database; CI re-renders
what you see. ORCID OAuth sign-in is planned (requires a small
token-exchange service; a pasted token needs none).

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
