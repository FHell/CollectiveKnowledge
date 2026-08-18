# CollectiveKnowledge → Knowledge Forge

A collaborative document engine for course books: students push text, the
instructor reviews rendered diffs, edits, approves and vouches, and
everyone discusses proposed edits — via a local CLI workflow or entirely
in the browser. The backend is a **self-hosted Forgejo**: repository,
accounts, changes and every discussion live on your own infrastructure.
Identity comes from **ORCID** — signing in with an ORCID iD is the one
way into the system, and the first sign-in auto-creates the forge
account with the ORCID iD as the username, so contributions carry a
verifiable scholarly identity.

**Key principles:** metadata lives in git (vouches are committed to
`meta/`), the forge stays unmodified, and the `book` CLI and the
in-browser client are both thin layers over git + the Forgejo REST API.

## The pieces

| Path | What it is |
|---|---|
| `chapters/`, `meta/` | the book itself: content + committed vouch records |
| `book/` | the `book` CLI (`pip install .`) — init, build, blame, diff, vouch, change, save, clone, submit, changes, review, comments, comment, approve — against a Forgejo/Gitea remote |
| `book/assets/` | site runtime: overlay (blame/vouch popups), `forge-client.js` + `web-actions.js` (browser client for the forge API: sign-in, discuss/vouch/edit, review bar, discussion threads) |
| `site/` | landing page + `build_site.sh`, the site assembly used by CI |
| `.forgejo/workflows/` | CI: per-PR rendered diff pages + full site deploy |
| `infra/` | docker-compose (Forgejo + Actions runner + nginx), bootstrap script — this is the deployment |
| `demo.sh` | one-command debug/demo server: site + stub forge + mocked ORCID sign-in + mock CI |
| `tests/` | `smoke.sh` (local), `remote_roundtrip.sh` (CLI round trip vs a stub forge), `web_e2e.sh` (headless-browser round trip: read thread, sign in — pasted token *and* mocked ORCID chain — reply, request changes) |
| `STUDENT_GUIDE.md` | one page: from nothing to a submitted change |
| `INSTRUCTOR_GUIDE.md` | reviewing from the CLI or the browser |
| `MVP_BUILD_PLAN.md` | the original MVP plan |
| `KNOWLEDGE_FORGE_ROADMAP.md` | the road ahead to a feature-complete Knowledge Forge |

## The published site

The deployed system serves a static site (see `infra/`): a landing page
with the live list of changes under review, the rendered book, and one
diff page per open change. Anonymous visitors can read everything —
book, authorship, vouches, diffs, discussions. Signing in is one click:
**site → forge (OAuth2+PKCE, no client secret) → ORCID**; a pasted forge
application token also works (e.g. for the CLI). Signed in:

- **tap a paragraph** on a book page to see blame + vouches and to
  **discuss** (opens a forge issue keyed to the paragraph's content
  hash), **vouch** (commits to `meta/vouches.yaml`, or opens a change
  when `main` is protected for you), or **edit** (branch + commit +
  change via the contents API);
- **on a diff page**, read the change's whole discussion under the
  rendered diff, reply in place, and (maintainers) approve / request
  changes / merge — always a merge commit, so paragraph authorship
  survives.

Git remains the database; CI re-renders what you see after every merge.

## Demo server (mocked auth, no Docker, no ORCID)

```sh
pip install -e .
./demo.sh            # site on http://127.0.0.1:8000, forge stub on :8001
```

One command runs the whole experience on localhost: this repo as the
demo book, a seeded change under review with a discussion and a
request-changes verdict, and the **auth workflow mocked** — the site's
real OAuth2+PKCE flow runs against the stub forge, whose ORCID step is
a picker of fictional personas (Josiah Carberry & friends); the chosen
persona's ORCID iD becomes your username, exactly as in production. A
mock CI loop renders diff pages for new changes within ~3 s and
rebuilds the book on merge. Everything is a temp dir; Ctrl-C tears it
down.

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
tests/remote_roundtrip.sh   # CLI round trip against a stub forge
pip install playwright      # once, for the browser test
tests/web_e2e.sh            # discussions on proposed edits, in a real browser
```
