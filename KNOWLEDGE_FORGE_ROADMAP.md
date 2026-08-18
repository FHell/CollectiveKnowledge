# Knowledge Forge — Roadmap to Feature Complete

**Goal.** Grow CollectiveKnowledge into **Knowledge Forge**: a full app where
anyone can read the published book (no login), and signed-in people can
**validate text** (vouch), **propose edits for approval**, and **discuss
changes with each other** — while the **offline CLI review workflow remains a
first-class, equal peer** of the web workflow at every step.

**Audience.** A fresh Claude session (or developer) executing one phase at a
time. Each phase lists concrete acceptance criteria. The plan assumes the
state described in "Where we are" below; Phase 0 verifies it.

---

## 1. Where we are (do not rebuild)

The MVP (`MVP_BUILD_PLAN.md`) and two follow-up iterations delivered:

| Area | Delivered |
|---|---|
| **CLI, local** | `book init / build / blame / diff [--render] / vouch / change / save / log` — AST-level rendered diffs, paragraph blame, vouches committed to `meta/vouches.yaml` |
| **CLI, remote** | `book clone / submit / changes / review / push-review / request-changes / approve [--vouch]` against GitHub **and** Forgejo/Gitea (`book/forge.py`, `book/remote.py`) |
| **Published site** | GitHub Pages: landing page, the rendered book, per-open-PR rendered AST-diff pages (`.github/workflows/pages.yml`, `site/build_site.sh`) |
| **Web read layer** | `overlay.js`: tap a paragraph → blame + vouches popup (from baked `blame.json` / `vouches.json`) |
| **Web write layer** | `forge-client.js` + `web-actions.js`: sign-in (pasted fine-grained token or GitHub OAuth), per-paragraph **discuss** (hash-keyed issue), **vouch** (commit or fallback PR), **edit** (branch + commit + PR via contents API); review bar on diff pages (approve / request changes / merge); open-changes list |
| **Auth service** | Cloudflare Worker token exchange (`worker/`): GitHub live, ORCID endpoint implemented but not wired into the frontend |
| **Self-host variant** | `infra/` docker-compose (Forgejo + runner + nginx), `.forgejo/workflows/` |
| **Tests** | `tests/smoke.sh` (local), `tests/remote_roundtrip.sh` + `tests/stub_forge.py` (remote round trip) |

**Standing architecture — keep it.** The site is static; the forge (GitHub or
Forgejo) is the backend; **git is the database** (vouches and metadata are
committed files); CI re-renders what you see; the only server-side code we own
is the ~100-line OAuth worker. This is what makes CLI/web parity cheap: both
are thin clients over the same git repo + forge API. Feature-complete
Knowledge Forge is reached by **extending this architecture, not by building
an app server**. Any phase that seems to need a database or backend must first
try: (a) bake the data into the static build from CI, (b) store it as a
committed file in `meta/`, or (c) read it live from the forge API. If a real
exception appears, it goes into the worker, stays stateless, and needs a
paragraph of justification in the PR.

---

## 2. What "feature complete" means

The three signed-in capabilities from the product statement, each taken to
"no asterisks", plus CLI parity:

1. **Reading (no login):** the book, its provenance (blame/vouch overlays),
   open changes and their rendered diffs, and all existing discussion are
   fully visible without signing in — and without burning API rate limits
   (today the changes list and discussion lookups hit the API anonymously at
   60 req/h; they must come baked into the build, live API only as refresh).
2. **Validating text:** any signed-in person can vouch; the site distinguishes
   *maintainer/validator* vouches from ordinary reader vouches (roles from a
   committed `meta/people.yaml`); stale vouches (paragraph edited since) are
   detected and surfaced; chapters show validation coverage.
3. **Proposing edits:** works for **any** signed-in GitHub user — today the
   web edit flow silently requires push access to the repo, because it
   creates branches in it. Fork-based flow closes this. Editing is
   paragraph-scoped with an (approximate) preview, handles conflicts, and
   every change lands as a PR that maintainers approve on the diff page or
   via `book approve`.
4. **Discussing:** conversation happens **in place** — paragraph threads
   readable and answerable inside the popup on the book page, change
   discussion readable and answerable on the rendered diff page — not via
   "opens a GitHub tab". GitHub issues/PR comments remain the storage.
5. **CLI of equal importance:** every capability above has a CLI verb, and
   the CLI works **offline**: `book sync` caches changes + discussions +
   review state locally; reviewing, diffing, drafting comments, vouching and
   approving can all be done disconnected and flushed on the next sync.

---

## 3. Feature matrix (the contract to build against)

| Capability | Anonymous web | Signed-in web | CLI online | CLI offline |
|---|---|---|---|---|
| Read book, blame, vouches | ✅ have | ✅ have | ✅ have (`build`, `blame`) | ✅ have |
| See open changes + rendered diffs | ⚠️ live-API only → bake | ✅ have | ✅ have (`changes`, `review`) | 🔲 via `sync` cache |
| Read paragraph discussions | ⚠️ search-API, flaky → bake | ⚠️ same | 🔲 `book discussions` | 🔲 via `sync` cache |
| Post in a discussion | — | ⚠️ opens tab → in-place | 🔲 `book discuss` | 🔲 outbox |
| Vouch | — | ✅ have | ✅ have (`vouch`) | ✅ commit, push on sync |
| Vouch staleness / coverage / roles | — | 🔲 | 🔲 `book vouches --stale` | 🔲 |
| Propose edit (has push access) | — | ✅ have (whole-file) | ✅ have (`submit`) | ✅ commit, push on sync |
| Propose edit (no push access) | — | 🔲 fork flow | 🔲 fork-aware `clone`/`submit` | 🔲 |
| Review: approve / request changes / merge | — | ✅ have | ✅ have | 🔲 outbox |
| Discuss a change (PR thread) | 🔲 read baked | 🔲 in-place on diff page | 🔲 `book comment` | 🔲 outbox |

✅ have · ⚠️ have with caveat · 🔲 to build

---

## 4. Phases

Order matters: 0 protects everything, 1–2 unlock the two biggest product
gaps (anyone-can-edit, discussion-in-place), 3–4 deepen validation and
editing, 5 delivers the offline CLI promise, 6–7 polish and productize.
Each phase is independently shippable.

### Phase 0 — Consolidation & test hardening (~2 days)

The web layer currently has zero automated coverage; every later phase
touches it.

1. **Browser e2e harness.** Playwright (Chromium is preinstalled in CI-like
   environments; pin `executablePath` fallback) driving the built site served
   from a local static server, against an extended `tests/stub_forge.py`.
   First tests: sign-in with pasted token, open paragraph popup, vouch
   (direct-commit path and PR-fallback path), propose edit, review bar
   approve+merge.
2. **Extend the stub forge** to cover what the coming phases need: issues
   list/create/comments, forks, `merge-upstream`, PR reviews, contents API
   409 conflicts.
3. **Worker smoke test** (`wrangler dev` / miniflare): `/exchange` happy path,
   origin rejection, error passthrough.
4. **Refactor for growth:** split `web-actions.js` (UI) from action logic so
   new features don't grow a 1000-line IIFE; keep zero-build-step vanilla JS
   (no bundler — the no-toolchain property is worth keeping).
5. Audit + fix any absolute-path leaks in generated HTML (regression from MVP
   pitfalls list).

**Acceptance:** `tests/e2e.sh` green locally and in CI alongside the two
existing suites; stub forge covers issues/forks/reviews/conflicts.

### Phase 1 — Everyone can propose edits: fork flow + identity (~3 days)

1. **Web fork flow.** In `forge-client.js`: on `proposeEdit`/`vouch` when the
   user lacks push access (detect via `GET /repos/:o/:r` `permissions.push`),
   run: `POST /repos/:o/:r/forks` (idempotent) → `POST
   /repos/:me/:r/merge-upstream` (sync fork main) → create branch in fork →
   `putFile` → cross-repo PR with `head: "login:branch"`. Poll fork
   readiness with capped backoff (fork creation is async).
2. **CLI fork flow.** `book clone` detects missing push access → offers to
   fork; sets `origin`=fork, `upstream`=canonical. `book submit` pushes to
   the fork and opens the cross-repo PR. `book review` already fetches
   `refs/pull/N/head`, which works for fork PRs unchanged — verify.
3. **Diff pages for fork PRs.** `site/build_site.sh` builds diffs from
   `git show` of fetched PR refs under `pull_request_target`; verify fork PR
   refs are fetched and rendered, and **keep the security invariant: PR
   content is data, never executed** (no `pip install` of PR code, no running
   PR workflows). Document the invariant in the workflow header.
4. **Sign-in polish.** OAuth scope: request `public_repo` (already) and add a
   clear consent explanation; keep pasted fine-grained PAT path. Sign-in
   state survives navigation (it does — localStorage) and shows role (from
   `meta/people.yaml`, Phase 3, stub it as "contributor" for now).
5. **ORCID wiring (identity, not access).** Frontend for the already-deployed
   `/orcid/exchange`: sign in with ORCID *in addition to* GitHub; store the
   verified ORCID iD; record it in vouches (`orcid:` field, matching a new
   optional field the CLI also writes) and in PR bodies. Writing still goes
   through GitHub.

**Acceptance (e2e):** a stub user with *no* push access proposes an edit in
the browser → fork → cross-repo PR; same round trip via CLI on a second
account; diff page renders for the fork PR; a vouch records an ORCID iD.

### Phase 2 — Discussion in place (~3 days)

Storage stays GitHub issues (paragraph threads) and PR comments (change
threads). What changes is that reading and replying happen inside the site.

1. **Bake discussion data at build time.** `site/build_site.sh` (with CI's
   `GITHUB_TOKEN`) fetches all issues labeled `paragraph-discussion` plus all
   open-PR comment threads → writes `discussions.json` (hash → [issue number,
   title, comment count, last activity]) and per-PR `comments.json`. The
   anonymous site reads only baked files — no more anonymous search-API calls
   (fixes rate-limit flakiness *and* GitHub search indexing lag). Also bake
   `changes.json` for the landing list, with live API as signed-in refresh.
2. **Label + link discipline.** Web `discuss` creates issues with the
   `paragraph-discussion` label and a machine-readable trailer (file, hash);
   CI backfills the label on legacy title-keyed issues. Merged/closed PR
   discussions stay readable via baked data.
3. **In-place threads on the book page.** Popup shows the paragraph's
   threads with comments inline (rendered as sanitized text — treat issue
   bodies as untrusted; no raw HTML injection), a reply box (POST comment),
   and "new thread". Thread indicator dot on paragraphs that have
   discussion (like the existing `bk-vouched` class).
4. **In-place discussion on diff pages.** Below the rendered diff: the PR
   conversation (issue comments + reviews, baked + live refresh when signed
   in), reply box, and request-changes/approve messages appearing as part of
   the thread. This is where "discussing edits with other logged in people"
   lives.
5. **CLI discussion verbs.** `book discussions [file]` (list threads),
   `book discuss <file> -p N -m "…"` (new thread, anchored to paragraph N's
   hash), `book comment <issue-or-pr> -m "…"`. `book review N` prints the
   PR thread before opening the diff.

**Acceptance (e2e):** two stub users hold a conversation on a paragraph and
on an open change without leaving the site; anonymous visitor sees both
conversations with zero authenticated API calls; the same threads are
readable and answerable via the CLI.

### Phase 3 — Validation at scale: roles, staleness, coverage (~2–3 days)

1. **Roles in git.** `meta/people.yaml`: login → {name, role:
   maintainer|validator|contributor, orcid}. Committed, PR-reviewed like
   everything else. `book build` bakes it into `people.json`.
2. **Vouch display by role.** Overlay and a per-chapter margin marker
   distinguish validator/maintainer vouches (e.g. solid check) from reader
   vouches (hollow check). Vouch records gain optional `orcid`.
3. **Staleness.** Vouches are hash-keyed, so an edited paragraph silently
   orphans its vouches today. `book build` computes per file: current-hash
   vouches vs orphaned vouches, and matches orphans to their nearest current
   paragraph (reuse the diff module's paragraph matcher against the vouch's
   recorded commit). Surface as: "edited since N vouched (date)" in the
   popup, and `book vouches --stale` in the CLI.
4. **Re-vouch nudges.** After `book approve --vouch` (CLI) or merge (web),
   prompt/list paragraphs whose vouches went stale in that merge.
5. **Coverage.** Chapter TOC and chapter header show validation coverage
   (x/y paragraphs vouched by a validator). Bake into `coverage.json`.

**Acceptance:** editing a vouched paragraph flips it to "stale" on the next
build with the old vouch visible as history; coverage numbers render;
`book vouches --stale` lists the same paragraphs the site shows.

### Phase 4 — Editing & review UX (~3 days)

1. **Paragraph-scoped editing.** The edit modal opens with the clicked
   paragraph's source pre-selected/scrolled (build emits source line spans
   per paragraph — extend `mystdoc`/`build` to record them in `blame.json`),
   with whole-file mode still available.
2. **Approximate live preview.** Client-side markdown-it + KaTeX preview in
   the modal, clearly labeled *approximate* — the CI-rendered AST diff page
   remains the source of truth (myst-parser is Python; do not attempt to run
   it in the browser or add a preview server).
3. **Conflict handling.** `putFile` 409 → refetch, tell the user what
   changed, offer re-apply; never silently overwrite. Same for vouch
   fallback path.
4. **Follow-up edits to an open change.** From a change's diff page, a
   signed-in author (or maintainer) can open the editor on the PR head
   branch and push another commit to the same PR — closing the loop on
   "request changes" rounds without the CLI.
5. **Review niceties.** Diff page: link each changed paragraph to its
   discussion anchor; show CI/diff freshness ("rendered from abc123");
   request-changes state visibly flips the change card on the landing list.

**Acceptance (e2e):** request-changes → author revises from the diff page →
diff re-renders → approve+merge, entirely in the browser; a conflicting
concurrent edit surfaces the conflict dialog instead of clobbering.

### Phase 5 — Offline-first CLI (~3 days)

The CLI must be a full peer that tolerates being disconnected — review on a
train, sync at the station.

1. **`book sync`.** Fetches git refs (main + open PR heads) and snapshots
   forge state — open PRs, review states, issue threads, comments — into
   `.book/cache/*.json` (gitignored). Prints what changed since last sync.
2. **Offline reads.** `book changes`, `book discussions`, `book review N
   --no-open` (and the rendered diff, which is already fully local) work
   from cache with a "as of <sync time>" banner when the forge is
   unreachable. Local operations (`diff`, `blame`, `build`, `vouch`,
   `save`) already work offline — keep it that way (no new network calls in
   local verbs).
3. **Outbox.** Write verbs (`comment`, `discuss`, `request-changes`,
   `approve`, `submit`) gain `--queue` behavior when offline: append the
   intended action to `.book/outbox.jsonl`; `book sync` replays the outbox
   (idempotently; approve/merge re-checks PR state first and skips with a
   warning if the change moved), then clears it. `book outbox` lists/edits
   pending actions.
4. **Vouch/approve offline.** Vouches are commits, so they queue naturally;
   `approve --vouch` offline queues the merge and performs vouching on the
   post-merge content at replay time (hash correctness — same rule as the
   MVP pitfall note).

**Acceptance:** scripted test — with the stub forge stopped, an instructor
syncs, reviews two changes, drafts comments, request-changes on one,
approves the other; stub restarted; `book sync` replays everything; forge
state matches the offline decisions.

### Phase 6 — Reader experience & site polish (~2–3 days)

1. **Navigation:** persistent TOC sidebar / prev-next links, mobile layout
   pass (the audience includes phone readers — the landing CSS already leans
   this way).
2. **Client-side search** over a baked `search.json` (lunr-style, no
   service).
3. **Accessibility pass:** overlay popup keyboard reachability and focus
   trapping in modals, contrast, `prefers-color-scheme` dark mode.
4. **PDF export:** `book build --pdf` via the print stylesheet + headless
   Chromium (already available for Playwright) rather than a LaTeX
   toolchain; CI attaches the PDF to the site.
5. **Performance/robustness:** ETag-aware fetch in `forge-client.js`;
   cache-bust baked JSON on deploy; graceful "site is rebuilding" states.

**Acceptance:** Lighthouse a11y ≥ 90 on book pages; search finds a phrase
from chapter 2; PDF artifact downloadable from the landing page.

### Phase 7 — Productization & parity audit (~2 days)

1. **Forgejo/Gitea parity audit.** Every feature added in Phases 1–5 has a
   `provider === "gitea"` path in `forge-client.js`/`book/forge.py` (forks,
   labels, reviews, comments) — extend `remote_roundtrip.sh` and the e2e
   suite to run against the gitea-mode stub too. Self-host CI workflows
   (`.forgejo/workflows/`) gain the same bake steps as `pages.yml`.
2. **Template-ability.** `book init --publish github:owner/repo` scaffolds a
   new book *with* the workflows, worker config stubs, and guides; mark the
   repo as a GitHub template; document "start your own Knowledge Forge" in
   the README.
3. **Release engineering.** Publish `book-cli` to PyPI from CI on tag;
   version the baked-JSON schema; CHANGELOG.
4. **Docs refresh.** STUDENT_GUIDE and INSTRUCTOR_GUIDE rewritten around the
   finished flows (web-first for students without git, CLI-first for
   instructors, offline section); adopt the **Knowledge Forge** name across
   README/site/landing.
5. **Security review.** Token handling writeup, worker origin allowlist,
   sanitization of forge-sourced text (Phase 2 item, re-audited),
   `pull_request_target` invariant, and a `SECURITY.md`.

**Acceptance:** a fresh repo created from the template deploys a working
forge with no code edits (only OAuth app + worker secrets); full e2e suite
green in both provider modes; PyPI install works.

---

## 5. Cross-cutting rules (apply to every phase)

- **Merge commits only** — squash destroys paragraph blame provenance.
- **Metadata lives in git** (`meta/`), never in a service.
- **Baked-then-live**: anonymous readers get CI-baked JSON; live API calls
  are a signed-in enhancement. No anonymous API dependency may be
  load-bearing.
- **Untrusted content**: anything fetched from the forge (issue bodies,
  comments, PR titles, usernames) is rendered as text or sanitized — never
  `innerHTML` of raw forge content. PR code is never executed by site CI.
- **CLI/web parity is a review checklist item**: a PR adding a web
  capability names its CLI counterpart (or ships it).
- **No build toolchain for the frontend**; vanilla JS modules, no bundler.
- **Every phase extends the stub forge + e2e suite first** (or alongside);
  no feature merges without a scripted regression.

## 6. Risks & open questions

| Risk | Mitigation / decision needed |
|---|---|
| GitHub search-API lag broke hash→issue lookup | Phase 2 removes the dependency (baked index + labels) |
| Fork-based PRs and `pull_request_target` are a classic CI security trap | Invariant is already right (build from main, PR content as data); Phase 1 documents and tests it |
| Anonymous rate limits (60/h/IP) | Baked-then-live rule; only signed-in refresh hits the API |
| myst preview in browser impossible (Python) | Accept approximate markdown-it preview; AST diff page stays truth |
| Outbox replay races (change merged/closed meanwhile) | Re-check state at replay, skip + warn, never force |
| ORCID users without GitHub cannot write | Accepted for feature-complete: ORCID = identity attestation, GitHub = write path. Revisit only if a real cohort needs it (would mean worker-mediated writes via a bot account — a deliberate architecture change) |
| Two YAML writers (CLI + browser) for `meta/vouches.yaml` | Keep append-format identical, covered by round-trip test; consider one-record-per-line JSONL migration if merge conflicts bite |

## 7. Definition of done — the demo script

1. **Anonymous phone visitor** reads a chapter, taps a paragraph: author,
   vouches (validator-marked), an existing discussion — all without login,
   all from static files.
2. **New reader** signs in with GitHub (OAuth) — no push access, never used
   git. Fixes a typo via the paragraph editor → fork → change appears on the
   landing list with a rendered diff.
3. **Second signed-in reader** disagrees with a wording choice on that diff
   page, comments; the author replies and revises from the diff page; the
   thread shows the whole exchange.
4. **Instructor on a train (offline)**: `book sync` was run at the station;
   `book changes`, `book review 7` (cached), drafts a request-changes on one
   change, approves another with `--vouch --queue`. Back online: `book sync`
   replays; the merge lands, vouches commit, the site rebuilds.
5. **A validator** vouches for the revised paragraph on the site; the
   chapter's coverage bar ticks up; the paragraph they *hadn't* re-checked
   shows "edited since vouched".
6. **Someone else** creates a new book from the template and has their own
   Knowledge Forge running the same day.

Total estimate: **~20 focused days** across seven independently shippable
phases.
