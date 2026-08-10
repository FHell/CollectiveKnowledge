# MVP Build Plan — Collaborative Document Engine

**Goal.** Students push text; the instructor reviews, edits, and approves it — via a local CLI workflow *or* a web workflow. Everything else (public reading UI, ORCID, comment overlays, PDF) is out of scope for this milestone.

**Audience of this document.** A fresh Claude session (or developer) with access to the existing `book` CLI codebase. The plan assumes the state described in "What already exists" below; Phase 0 verifies that assumption.

---

## 1. What already exists (do not rebuild)

A working **local-only** Python CLI `book`, wrapping git, with:

| Command | Status |
|---|---|
| `book init` | working — scaffolds repo (`book.toml`, `myst.yml`, `_toc.yml`, `chapters/`, `meta/`) |
| `book build` | working — MyST → docutils AST → HTML via custom translator; static site in `_build/html/` with overlay.js, blame.json, vouches.json |
| `book blame` | working — paragraph-level, wraps `git blame` |
| `book diff [ref]` | working — sentence-level terminal diff |
| `book diff [ref] --render` | working — **AST-level rendered HTML diff** (myst-parser → flattened block nodes → `SequenceMatcher` → inline-level diff of paragraph pairs → custom `diff_insert`/`diff_delete` docutils nodes → `<ins>`/`<del>` HTML with typeset math) |
| `book vouch` | working — records to `meta/vouches.yaml`, commits |
| `book change new\|list\|switch` | working — namespaced branches (`username/description`) |
| `book log` | working |

Known-good engineering decisions baked in: myst-parser (Python), *not* the JS mystmd CLI; sections flattened before diffing; AST-level equality check to skip frontmatter-only differences; no per-file `sys.path` hacks.

**Missing for MVP:** everything remote. There is no server, no push/submit flow, no PR integration, no way for the instructor to pull in and review a student's change, and no published site.

---

## 2. MVP definition

### Actors
- **Student** — writes/edits chapters, submits changes. Should never need raw git branching knowledge.
- **Instructor** (maintainer) — lists pending changes, reviews rendered diffs, edits the change directly if needed, requests revisions or approves+merges, optionally vouches.

### The two workflows to deliver

**Local workflow (both sides):**
```
STUDENT                                   INSTRUCTOR
book clone <url>
edit chapters/…                           book changes            # list open PRs
book change new "fix-derivation"          book review 12          # fetch branch, open rendered diff
book save -m "…"   (add+commit)           edit files, book save   # instructor edits student's branch
book submit                               book request-changes 12 -m "…"   # or:
    → push branch, open PR                book approve 12 [--vouch]        # merge + rebuild + vouch
```

**Web workflow (mostly instructor):**
- Forgejo PR page = the change (title, discussion, request-changes, merge button).
- CI attaches a **rendered AST-diff** page to every PR (link posted as PR comment).
- On merge to `main`, CI rebuilds and deploys the static book site.

This deliberately uses Forgejo's PR UI as the web review surface for MVP — no custom review frontend yet. The one custom web artifact is the rendered diff page, which is the thing Forgejo cannot do.

### Explicit non-goals (MVP)
- Custom web reader with click-to-vouch / comment sidebar interactions beyond what `book build` already emits.
- `meta/comments.yaml` workflows (PR comments on Forgejo suffice).
- ORCID identity, PDF export, vouch-staleness UI polish, multi-book hosting.

---

## 3. Architecture for the MVP

```
Forgejo (unmodified, self-hosted, Docker)
├── repo hosting, users (instructor + students), branch protection on main
├── PRs = changes; PR comments = ephemeral discussion
├── Forgejo Actions (CI):
│     on PR open/sync  → build rendered diff → publish → comment link on PR
│     on push to main  → book build → deploy _build/html/
└── API consumed by the CLI (token auth)

book CLI (extended)
├── remote config:  ~/.config/book/config.toml  (forgejo url, user, token)
├── submit / changes / review / approve / request-changes  (new)
└── everything local stays as-is

Static hosting
└── nginx (or Caddy) serving:
      /            → latest built book (main)
      /diffs/<pr>/ → rendered diff per PR (CI output)
```

Key principle preserved: **metadata in git** (vouches committed to `meta/`), **Forgejo unmodified**, CLI is a thin layer over git + Forgejo REST API.

---

## 4. Phases

### Phase 0 — Audit & test harness (½ day)
1. Read the existing CLI code end to end. Map commands → modules. Note where git is shelled out vs. library-called.
2. Confirm the rendered-diff entry point is callable as a function (needed by CI), not only via CLI. If not, refactor: `book.diff.render_diff(repo_path, base_ref, head_ref, out_path) -> Path`.
3. Add a smoke-test script (`tests/smoke.sh`) that: creates a temp repo, `book init`, adds a chapter, builds, makes a change branch, edits, asserts `book diff main --render` produces HTML containing `<ins>`/`<del>`. This is the regression guard for everything below.
4. Confirm `book build` output is fully static (no local server assumptions in overlay.js paths — must work under a URL prefix).

**Acceptance:** smoke test green; diff callable programmatically.

### Phase 1 — Forgejo instance (½–1 day)
1. `docker-compose.yml` with Forgejo (pin a current stable tag) + a volume; enable Forgejo Actions with one runner container.
2. Bootstrap script (`infra/bootstrap.sh`): create instructor admin account, create org/repo, protect `main` (no direct pushes except instructor; require PR), create student accounts or an invite flow, issue API tokens.
3. Push the existing book repo as the canonical repo.

**Acceptance:** student account can clone over HTTPS/SSH, cannot push to `main`, can push `username/*` branches.

Notes for the builder:
- Branch protection: protect `main` only. Do **not** restrict branch creation — students need `<username>/*`.
- Decide auth: HTTPS + token is simplest for students; document it in README.

### Phase 2 — CLI remote commands (1–2 days)
New module `book/forge.py`: minimal Forgejo REST client (requests): `create_pr`, `list_prs`, `get_pr`, `merge_pr`, `post_comment`, `request_review_state`. Token from config file or `BOOK_TOKEN` env.

New/changed commands:

| Command | Behavior |
|---|---|
| `book clone <url>` | `git clone` + write local config (username inferred/prompted). Sets fetch refspec to exclude other users' branches (`+refs/heads/main`, `+refs/heads/<me>/*`) per the existing design. |
| `book save [-m msg]` | `git add -A && git commit`. Sugar so students never type git. Auto-message from changed files if `-m` omitted. |
| `book submit` | Ensure on a `<me>/…` branch (error with hint otherwise) → push → create PR (base `main`) if none exists, else just push. Print PR URL + rendered-diff URL. Idempotent. |
| `book changes` | **Replace** local-branch listing with Forgejo PR listing: number, author, title, state, updated. Keep `--local` flag for old behavior. |
| `book review <n>` | `git fetch origin pull/<n>/head` (Forgejo supports `refs/pull/<n>/head`) into `review/pr-<n>` → checkout → run rendered diff vs `origin/main` → open in browser. |
| `book request-changes <n> -m "…"` | Post PR review/comment with state `REQUEST_CHANGES`. |
| `book approve <n> [--vouch] [--note "…"]` | Merge PR via API (merge commit, not squash — preserves student authorship in blame). Then `git pull main`. If `--vouch`: run existing vouch logic scoped to the files changed by the PR, commit to `meta/`, push. |

Instructor-edits-the-change flow: after `book review <n>`, the instructor is on `review/pr-<n>`; `book save` + `book push-review <n>` pushes back to the PR's head branch (needs write access to student branch — Forgejo allows repo admins; verify in Phase 1, else fall back to instructor pushing a `frank/pr-<n>-edits` branch and noting it in the PR).

**Acceptance (scripted against a live test Forgejo):** full round trip — student submits, instructor lists, reviews with rendered diff, edits, approves with vouch; `main` contains both commits, `meta/vouches.yaml` updated, blame attributes student correctly.

### Phase 3 — CI: diff previews + site deploy (1 day)
Forgejo Actions workflows in the book repo:

`.forgejo/workflows/pr-diff.yml` — on `pull_request` (open/synchronize):
1. Checkout head + fetch base.
2. `pip install` the book tool (publish it as an installable package — add `pyproject.toml` in Phase 0 if missing).
3. `book diff origin/main --render -o diff.html` (add `-o` flag if absent).
4. Publish `diff.html` to the static host under `/diffs/pr-<n>/` (simplest: `rsync`/`scp` to the nginx volume, or a tiny upload endpoint; choose based on where the runner lives — same host ⇒ shared volume is fine).
5. Post/update a single PR comment: "Rendered diff: <url>" (find-and-edit existing bot comment to avoid spam).

`.forgejo/workflows/deploy.yml` — on push to `main`:
1. `book build`
2. Sync `_build/html/` to the nginx web root.

**Acceptance:** opening a PR yields a working rendered-diff link within ~1 min; merging updates the live book.

### Phase 4 — Nginx + glue, docs, onboarding (½ day)
1. Add nginx to `docker-compose.yml`: serves book at `/`, diffs at `/diffs/`, reverse-proxies Forgejo at `/git/` (or a subdomain — subdomain is less path-rewriting pain; prefer `git.example.org` + `book.example.org` if DNS allows).
2. `STUDENT_GUIDE.md` in the repo root: install tool (`pipx install …`), clone, edit, `book change new`, `book save`, `book submit`; screenshot of the PR + diff link. One page max.
3. `INSTRUCTOR_GUIDE.md`: `book changes` / `review` / `approve` and the equivalent web-only path (Forgejo PR page + diff link + merge button) so review works from any machine with a browser.

**Acceptance:** a new student can go from nothing to a submitted PR following only STUDENT_GUIDE.md.

---

## 5. Implementation notes & pitfalls

- **Squash vs merge:** use merge commits. Squash would collapse authorship and break paragraph-blame provenance, which is a core value of the project.
- **`refs/pull/<n>/head`:** verify Forgejo exposes these refs for fetch (it does, Gitea-compatible); if unavailable, fall back to fetching the head branch by name from the PR JSON.
- **Vouch anchoring on approve:** vouches are keyed by paragraph content hash; run vouching *after* the merge and pull, on the merged content, so hashes match `main`.
- **Diff rendering in CI:** myst-parser rendering needs no network — this was the reason for dropping mystmd; keep it that way (no CDN fetches at build time; MathJax may load client-side in the HTML, which is fine).
- **Path prefixes:** the diff pages and book pages will be served under prefixes (`/diffs/pr-3/`). Audit generated HTML for absolute paths (`/_meta/style.css`) and make asset paths relative.
- **Idempotency:** `book submit` re-run must not create duplicate PRs; CI comment must update in place.
- **Config precedence:** env var > repo-local `.book/config` > `~/.config/book/config.toml`. Never commit tokens.
- **Windows students:** if any exist, test `book` on Windows or state "WSL required" in the guide up front.

## 6. Suggested build order for the executing session

1. Phase 0 audit + smoke test (protects everything).
2. Phase 2 CLI against a throwaway local Forgejo (Phase 1 docker-compose can be spun up first in bare-bones form — these interleave naturally).
3. Phase 3 CI.
4. Phase 4 polish + guides.

Estimated total: **3–5 focused days.**

## 7. Definition of done (end-to-end demo script)

1. Instructor: `docker compose up`, bootstrap, push book repo.
2. Student (fresh machine): install tool, clone, `book change new "add-example"`, edit a paragraph including a formula, `book save`, `book submit`.
3. PR appears; CI posts rendered-diff link; diff shows the changed math symbol individually highlighted.
4. Instructor (laptop): `book changes` → `book review 1` → tweaks wording → `book save` → `book push-review 1`.
5. Instructor: `book approve 1 --vouch --note "checked derivation"`.
6. Live site at `/` shows the merged text; clicking the paragraph shows student authorship (blame) and the instructor's vouch.
7. Same review, done again for PR 2 entirely in the browser (Forgejo UI + diff link + merge button), no CLI.

If all seven steps pass, the MVP is done.
