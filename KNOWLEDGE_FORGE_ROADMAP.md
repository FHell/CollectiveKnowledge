# Knowledge Forge — Roadmap to Feature Complete

**Goal.** Grow CollectiveKnowledge into **Knowledge Forge**: a full app
where anyone can read the published book (no login), and signed-in people
can **validate text** (vouch), **propose edits for approval**, and
**discuss those edits with each other** — while the **offline CLI review
workflow remains a first-class, equal peer** of the web workflow at every
step.

**Audience.** A fresh Claude session (or developer) executing one phase at
a time. Each phase lists concrete acceptance criteria.

---

## 1. The architecture decision: one self-hosted forge

The backend is a **self-hosted Forgejo instance** (`infra/`), full stop.
It hosts the repository, the accounts, the changes (PRs), and — the point
of self-hosting — **the discussions themselves**: every comment lives on
infrastructure the course controls, not on a third-party platform. GitHub
was used as a convenience backend in the prototype and has been dropped:
the OAuth token-exchange worker, the GitHub Pages deployment and all
GitHub API code paths are gone.

What this buys:

- **Genuine hosting of discussion.** Threads on changes and paragraphs
  are course data, on course hardware, exportable with the forge.
- **No third-party coupling.** No rate limits on anonymous reads, no
  search-API indexing lag, no external OAuth apps, no client-secret
  service: sign-in is a public OAuth2 + PKCE app on our own forge (or a
  pasted token), so the last piece of "our own server-side code" (the
  Cloudflare worker) is deleted.
- **Everyone who matters has an account.** Contributors self-register by
  signing in, so the whole fork-based contribution machinery a
  third-party forge would force is unnecessary: participants push
  `username/*` branches to the one repository.
- **ORCID is the account service** — and the only way in. Forgejo
  consumes ORCID as an OpenID Connect authentication source; the first
  ORCID sign-in auto-creates the forge account with the **ORCID iD as
  the username**, password/form login stays off, and the site's sign-in
  chain is site → forge (OAuth2+PKCE) → ORCID. Contributions,
  discussions and vouches thereby carry verifiable scholarly identity,
  with zero identity code in this repo — it is Forgejo configuration
  (`infra/`).

Standing principles, unchanged: the published site is **static** (nginx),
the browser client and the CLI are both thin layers over git + the
Forgejo REST API, **git is the database** (vouches and metadata are
committed files in `meta/`), the forge stays unmodified, and CI re-renders
what you see. Any feature that seems to need an app server must first
try: (a) bake the data into the static build from CI, (b) store it as a
committed file in `meta/`, or (c) read/write it live via the forge API.

## 2. Where we are

Delivered by the MVP plus the iterations since (do not rebuild):

| Area | Delivered |
|---|---|
| **CLI, local** | `book init / build / blame / diff [--render] / vouch / change / save / log` — AST-level rendered diffs, paragraph blame, vouches committed to `meta/vouches.yaml` |
| **CLI, remote** | `book clone / submit / changes / review / push-review / request-changes / approve [--vouch]` against Forgejo (`book/forge.py`, `book/remote.py`) |
| **CLI, discussion** | ✅ new: `book comments N` (opening post + comments + review verdicts, chronological), `book comment N -m`, and `book review N` prints the thread before opening the diff |
| **Published site** | landing page (live open-changes list), the rendered book, per-open-PR diff pages; built by `site/build_site.sh`, deployed by `.forgejo/workflows/deploy.yml` (atomic swap), single diff pages refreshed by `pr-diff.yml` within ~1 min |
| **Web read layer** | tap a paragraph → blame + vouches (baked `blame.json` / `vouches.json`) |
| **Web write layer** | sign-in (pasted Forgejo token or one-click OAuth2+PKCE — no secret, no extra service); per-paragraph discuss / vouch / edit; review bar on diff pages (approve / request changes / merge) |
| **Discussions on proposed edits** | ✅ new: every diff page shows the change's full discussion below the rendered diff — opening post, comments, review verdicts as badges — readable anonymously, replyable in place when signed in; request-changes/approve/merge refresh the thread |
| **CI security invariant** | ✅ new: both workflows build tool + site from `main` only; PR content is read as data (`git show`), never installed or executed |
| **Tests** | `tests/smoke.sh` (local), `tests/remote_roundtrip.sh` (CLI round trip incl. discussion against the stub forge), ✅ new `tests/web_e2e.sh` + `web_discussion_test.py` (headless Chromium: read thread anonymously, sign in, reply in place, request changes — verified against the stub forge's state) |
| **Self-host infra** | docker-compose (Forgejo + runner + nginx) with CORS for the site origin; `bootstrap.sh` provisions the admin, branch protection, CI secrets, and the public OAuth2 (PKCE) app |
| **Identity** | ✅ new: ORCID-only sign-in wired at the infra level — compose config (external-registration-only, password form off, username = ORCID iD) + `bootstrap.sh` registers the ORCID OIDC source; site button labeled via `book.toml [oauth] label` |
| **Demo server** | ✅ new: `./demo.sh` runs the full experience on localhost with the auth workflow mocked — the stub forge serves the real OAuth2+PKCE endpoints with a fictional-persona picker in ORCID's place, implements the contents/branches/issues APIs (so web edit/vouch/discuss work), renders read-only HTML thread views, and a mock CI loop produces diff pages and rebuilds on merge; the browser e2e also covers the mocked sign-in chain |

## 3. What "feature complete" means

1. **Reading (no login):** book, provenance (blame/vouch overlays), open
   changes, rendered diffs, and all discussion — fully visible without
   signing in. *(Largely done; paragraph-level threads still open in the
   forge UI rather than in place — see Phase D.)*
2. **Validating text:** any signed-in person can vouch; validator/
   maintainer vouches are distinguished (roles from a committed
   `meta/people.yaml`); stale vouches (paragraph edited since) are
   detected and surfaced; chapters show validation coverage.
3. **Proposing edits:** paragraph-scoped editing with an (approximate)
   preview and conflict handling; every change lands as a PR reviewed on
   the diff page or via `book approve`; authors can push revisions from
   the diff page during request-changes rounds.
4. **Discussing:** conversation happens in place — on diff pages *(done)*
   and in the paragraph popup on book pages *(reading/replying inline
   still to do)*. The forge hosts it all.
5. **CLI of equal importance:** every capability has a CLI verb *(threads:
   done)* and works **offline**: `book sync` caches changes + discussions
   + review state; reviewing, drafting comments, vouching and approving
   can be done disconnected and flushed on the next sync.

## 4. Feature matrix (the contract to build against)

| Capability | Anonymous web | Signed-in web | CLI online | CLI offline |
|---|---|---|---|---|
| Read book, blame, vouches | ✅ | ✅ | ✅ | ✅ |
| See open changes + rendered diffs | ✅ | ✅ | ✅ | 🔲 via `sync` cache |
| Read discussion on a change | ✅ diff page | ✅ | ✅ `comments` | 🔲 via `sync` cache |
| Reply in a change discussion | — | ✅ in place | ✅ `comment` | 🔲 outbox |
| Read paragraph discussions | ⚠️ links to forge | ⚠️ links to forge | 🔲 `discussions` | 🔲 |
| Post in a paragraph discussion | — | ⚠️ create only, reply on forge | 🔲 `discuss` | 🔲 outbox |
| Vouch | — | ✅ | ✅ | ✅ commit, push on sync |
| Vouch staleness / coverage / roles | — | 🔲 | 🔲 `vouches --stale` | 🔲 |
| Propose edit | — | ✅ (whole-file) | ✅ `submit` | ✅ commit, push on sync |
| Revise a change during review | — | 🔲 from diff page | ✅ `push-review` | 🔲 |
| Review: approve / request changes / merge | — | ✅ | ✅ | 🔲 outbox |

✅ have · ⚠️ have with caveat · 🔲 to build

## 5. Phases

Each phase is independently shippable. Suggested order: A → D → B → C →
E → F (accounts first — nothing else matters if people can't get in).

### Phase A — Prove the ORCID chain end to end (~2 days)

The decision is made and the configuration is in place (compose +
bootstrap); what remains is verifying it against real services and
smoothing the first-contact experience.

1. **Live verification.** Rehearse the full chain against a real
   Forgejo over HTTPS with the **ORCID sandbox**
   (`ORCID_DISCOVERY_URL`): sign-in → auto-registration → username is
   the ORCID iD → first-login email/username confirmation → application
   token generation → CLI clone/submit. Fix whatever the rehearsal
   surfaces (claim mapping, redirect URIs, cookie/SameSite issues).
2. **Sign-in polish on the site.** Verify the PKCE flow (WebCrypto needs
   a secure context); when Forgejo has exactly one auth source and no
   password form, confirm the forge login page effectively forwards to
   ORCID so the user experiences one hop; handle token expiry by
   degrading to re-auth cleanly.
3. **First-contact UX.** The site's sign-in dialog explains "your ORCID
   iD is your account" and links to ORCID registration for people
   without one; display names: prefer the ORCID-supplied full name over
   the raw iD in overlays and threads where available (`people.json`
   groundwork for Phase C).
4. **Admin story.** Document + rehearse ORCID-linking the bootstrap
   admin account (see `infra/README.md`) so no password sign-in remains
   in day-to-day use.

**Acceptance:** a person with only an ORCID iD (sandbox) goes from
never-seen-the-site to a submitted, discussed change — browser and CLI —
with no instructor involvement and no password anywhere.

### Phase B — Editing & review UX (~3 days)

1. **Paragraph-scoped editing.** The edit modal opens with the clicked
   paragraph's source pre-selected/scrolled (build emits source line
   spans per paragraph into `blame.json`), whole-file mode still
   available.
2. **Approximate live preview.** Client-side markdown-it + KaTeX preview
   in the modal, clearly labeled *approximate* — the CI-rendered AST diff
   page remains the source of truth (myst-parser is Python; do not run it
   in the browser or add a preview server).
3. **Conflict handling.** Contents-API 409 → refetch, show what changed,
   offer re-apply; never silently overwrite. Same for the vouch fallback
   path.
4. **Revise from the diff page.** The change's author (or a maintainer),
   signed in, opens the editor on the PR head branch and pushes another
   commit to the same change — closing request-changes rounds without the
   CLI. The diff page shows "rendered from <sha>" freshness.

**Acceptance (e2e):** request changes → author revises from the diff page
→ diff re-renders → approve + merge, entirely in the browser; a
conflicting concurrent edit surfaces the conflict dialog instead of
clobbering.

### Phase C — Validation at scale: roles, staleness, coverage (~2–3 days)

1. **Roles in git.** `meta/people.yaml`: login (= ORCID iD) → {name,
   role: maintainer|validator|contributor}. Committed and PR-reviewed
   like everything else; baked into `people.json` by `book build` —
   also the map from raw ORCID iDs to display names everywhere on the
   site.
2. **One identity per vouch.** Web vouches record the forge login
   (ORCID iD); CLI vouches currently record git `user.name` — align the
   CLI on the configured forge username so both writers produce
   ORCID-keyed records.
3. **Vouch display by role.** Overlay and chapter margin distinguish
   validator/maintainer vouches from reader vouches.
4. **Staleness.** Vouches are hash-keyed, so an edited paragraph silently
   orphans its vouches today. `book build` matches orphaned vouches to
   their nearest current paragraph (reuse the diff module's matcher
   against the vouch's recorded commit) and surfaces "edited since N
   vouched (date)"; `book vouches --stale` lists the same.
5. **Re-vouch nudges** after merges that stale existing vouches (CLI
   prompt on `approve --vouch`; list on the diff page after merge).
6. **Coverage.** Chapter TOC and header show validation coverage
   (x/y paragraphs vouched by a validator), baked into `coverage.json`.

**Acceptance:** editing a vouched paragraph flips it to "stale" on the
next build with the old vouch visible as history; coverage renders; CLI
and site agree on the stale list.

### Phase D — Paragraph discussions in place (~2 days)

Diff-page threads are done; paragraph threads still bounce to the forge
UI.

1. **Inline threads in the popup.** The paragraph popup lists its
   discussions with comments readable inline (plain-text rendering — all
   forge-sourced text stays sanitized) and a reply box; "new thread"
   keeps the current issue-creation flow.
2. **Robust anchoring.** Discussion issues get a `paragraph` label and a
   machine-readable trailer (file + hash); `book build` bakes a
   hash → issues index (`discussions.json`) so book pages don't need a
   per-paragraph search call; live API refresh on popup open.
3. **Thread indicators.** Paragraphs with discussion get a marker (like
   the existing `bk-vouched` styling) so conversation is discoverable.
4. **CLI:** `book discussions [file]` and `book discuss <file> -p N -m`.

**Acceptance (e2e):** two users converse on a paragraph without leaving
the book page; anonymous visitors read the same thread inline; the same
thread is readable and answerable via the CLI.

### Phase E — Offline-first CLI (~3 days)

Review on a train, sync at the station.

1. **`book sync`.** Fetches git refs (main + open PR heads) and snapshots
   forge state — open PRs, review states, threads — into
   `.book/cache/*.json` (gitignored). Prints what changed since last sync.
2. **Offline reads.** `book changes`, `book comments`, `book review N
   --no-open` work from the cache with an "as of <sync time>" banner when
   the forge is unreachable. Local verbs (`diff`, `blame`, `build`,
   `vouch`, `save`) stay network-free.
3. **Outbox.** Write verbs (`comment`, `request-changes`, `approve`,
   `submit`) queue to `.book/outbox.jsonl` when offline; `book sync`
   replays idempotently (re-checks PR state first; skips with a warning
   if the change moved). `book outbox` lists/edits pending actions.
4. **Vouch/approve offline.** Vouches are commits, so they queue
   naturally; a queued `approve --vouch` vouches the post-merge content
   at replay time so hashes match `main`.

**Acceptance:** scripted test — stub forge stopped, instructor reviews
two cached changes, drafts a comment and a request-changes, queues an
approve; stub restarted; `book sync` replays everything; forge state
matches the offline decisions.

### Phase F — Reader experience, ops & productization (~4 days)

1. **Reader polish:** persistent TOC sidebar / prev-next links, mobile
   pass, client-side search over a baked index, accessibility pass
   (keyboard-reachable popups, focus-trapped modals, contrast, dark
   mode), `book build --pdf` via headless Chromium print.
2. **Resilience:** bake a `changes.json` snapshot at deploy time so the
   landing list renders even if the forge is briefly down; live API as
   refresh.
3. **Ops for self-hosting** (now that we host the discussions, we own
   their durability): documented backup/restore of the Forgejo volume +
   the git repos, upgrade procedure, HTTPS/reverse-proxy recipe, resource
   sizing for a course.
4. **Productization:** `book init --publish` scaffolds a new book with
   workflows + infra stubs; publish `book-cli` to PyPI from CI on tag;
   rewrite the guides around the finished flows; adopt the **Knowledge
   Forge** name across repo/site; `SECURITY.md` (token handling, CORS
   scope, sanitization of forge-sourced text, the CI PR-content-as-data
   invariant).

**Acceptance:** a fresh course deploys from scratch following only
`infra/README.md`; backup/restore rehearsed; Lighthouse a11y ≥ 90;
full test suite green.

## 6. Cross-cutting rules (apply to every phase)

- **Merge commits only** — squash destroys paragraph blame provenance.
- **Metadata lives in git** (`meta/`), never in a service of our own.
- **The forge stays unmodified** — features compose git + REST API only.
- **Untrusted content:** anything fetched from the forge (comments,
  titles, usernames) renders as plain text or sanitized — never raw HTML.
  CI never installs or executes PR content.
- **CLI/web parity is a review checklist item:** a change adding a web
  capability names its CLI counterpart (or ships it) — and vice versa.
- **No build toolchain for the frontend** — vanilla JS, no bundler.
- **Every feature lands with a scripted regression** (stub forge for the
  CLI, Playwright for the browser).

## 7. Risks & open questions

| Risk | Mitigation / decision needed |
|---|---|
| ORCID outage ⇒ nobody can sign in | Reading is unaffected (static site); existing sessions and application tokens keep working — tokens are the write-path fallback; document in the ops runbook |
| ORCID OIDC provides no email claim | Forgejo's one-time completion form on first login (rehearsed in Phase A); acceptable friction |
| PKCE token endpoint CORS varies across Forgejo versions | `[cors]` enabled in compose; pasted token is the always-works fallback; verify per release in Phase A |
| Self-hosted forge down ⇒ interactive layer dark | Site stays readable (static); Phase F bakes snapshots for the landing list; ops runbook |
| We now own discussion durability | Phase F backup/restore of the Forgejo volume is non-optional |
| myst preview in the browser impossible (Python) | Approximate markdown-it preview, AST diff page stays truth |
| Outbox replay races (change merged/closed meanwhile) | Re-check state at replay, skip + warn, never force |
| Two YAML writers (CLI + browser) for `meta/vouches.yaml` | Append-format identical, covered by round-trip test; revisit as JSONL if merge conflicts bite |
| Paragraph-hash anchoring breaks on edits | Same mechanism as vouch staleness (Phase C matcher) reused for discussions in Phase D |

## 8. Definition of done — the demo script

1. **Anonymous phone visitor** reads a chapter, taps a paragraph (author,
   vouches, discussion), opens a change's diff page and reads the whole
   debate under it — no login anywhere.
2. **New participant** clicks "Sign in with ORCID" — their ORCID iD is
   their account, created on the spot — and fixes a typo via the
   paragraph editor; the change appears on the landing list with a
   rendered diff, attributed to their ORCID iD.
3. **Another participant** disagrees with a wording choice **on the diff
   page**, replies in place; the author revises from the same page; the
   thread shows the whole exchange next to the always-current diff.
4. **Instructor on a train (offline):** `book sync` ran at the station;
   `book changes`, `book review 7`, `book comments 7` all work from
   cache; a request-changes and an `approve --vouch` are queued. Back
   online: `book sync` replays; the merge lands; the site rebuilds.
5. **A validator** vouches for the revised paragraph; the chapter's
   coverage ticks up; an unrechecked paragraph shows "edited since
   vouched".
6. **The course ends:** the instructor backs up the forge volume — book,
   history, vouches and every discussion — onto a disk they own.

Total estimate: **~16 focused days** across six phases.
