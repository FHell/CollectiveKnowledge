# Infrastructure

One host, three containers (see `docker-compose.yml`). The self-hosted
Forgejo is **the** backend of the whole system: it hosts the repository,
the accounts, the changes (PRs) and every discussion on them — nothing
lives on a third-party service.

| Service | Role | Port |
|---|---|---|
| forgejo | the backend: repos, users, changes, discussions, Actions | 3000 (HTTP), 2222 (SSH) |
| runner  | executes `.forgejo/workflows/` | — |
| nginx   | serves the published site (landing `/`, book `/book/`, diffs `/diffs/pr-N/`) | 8080 |

The only glue between CI and the web server is the shared `book-site`
volume: the deploy workflow writes the whole site to `/site/current`
(atomic swap), the PR workflow refreshes single diff pages under
`/site/current/diffs/pr-<n>/`, and nginx serves it read-only.

The published site's browser client talks straight to the Forgejo API
(reading discussions works anonymously; writing needs a sign-in). Since
site and forge are different origins, `docker-compose.yml` enables
Forgejo's `[cors]`; set `SITE_ORIGIN=https://book.example.org` in the
compose environment to lock it down to the site's origin (default `*`).

## Accounts: ORCID is the account service

Participants do not get passwords: **signing in with ORCID is the one
way into the system.** Forgejo consumes ORCID as an OpenID Connect
authentication source, and the first ORCID sign-in auto-creates the
forge account with the **ORCID iD as the username** — so authorship,
reviews, discussions and vouches all carry a verifiable scholarly
identity. Password/form registration is off; the password sign-in form
is hidden by default (`FORGEJO_PASSWORD_SIGNIN=true` re-enables it for
ORCID-less local testing).

Setup (once):

1. Register a **public API client** at https://orcid.org/developer-tools
   (any ORCID account can). Redirect URI:
   `https://git.example.org/user/oauth2/orcid/callback` — your
   `FORGEJO_ROOT_URL` + `/user/oauth2/orcid/callback`.
2. Export `ORCID_CLIENT_ID` and `ORCID_CLIENT_SECRET` before running
   `bootstrap.sh` (it registers the auth source; re-run is fine), or add
   the source later the same way.
3. For rehearsals, `ORCID_DISCOVERY_URL=https://sandbox.orcid.org/.well-known/openid-configuration`
   points the source at the ORCID sandbox.

First-login experience: ORCID's OIDC claims carry the iD and name but
no email address, so Forgejo asks the new arrival to confirm their
(prefilled) username and enter an email once; everything afterwards is
one click. The sign-in chain for the published site is
**site → forge (OAuth2+PKCE) → ORCID**, so the site never sees ORCID
credentials and needs no ORCID configuration of its own beyond the
button label in `book.toml`.

Admin access: the bootstrap instructor account is a local admin. Either
do admin work via `docker compose exec forgejo forgejo …` and API
tokens, or — to use the admin web UI — start once with
`FORGEJO_PASSWORD_SIGNIN=true`, sign in, link your ORCID under
*Settings → Linked accounts*, then drop the flag: your ORCID sign-in
now lands on the admin account.

## Setup

1. **Start services**

   ```sh
   cd infra
   FORGEJO_ROOT_URL=https://git.example.org/ docker compose up -d
   ```

   For a local test run, `FORGEJO_PASSWORD_SIGNIN=true docker compose
   up -d` works without any ORCID client (Forgejo on
   `http://localhost:3000`, book on `http://localhost:8080`).

2. **Bootstrap accounts, repo, branch protection, tokens**

   ```sh
   ./bootstrap.sh frank course book alice bob carol
   ```

   Creates the instructor admin (`frank`), the **ORCID authentication
   source** (when `ORCID_CLIENT_ID`/`ORCID_CLIENT_SECRET` are exported —
   see the accounts section above), org `course`, repo `course/book`,
   protects `main` (PRs only; instructor may push — do NOT restrict
   branch creation, participants need `<username>/*`), the `CI_TOKEN`
   secret / `SITE_URL` variable the workflows use, and a **public OAuth2
   app** (PKCE, no secret) for one-click sign-in on the published site —
   put the printed `client_id` into `book.toml` under `[oauth]`.
   The trailing `[student ...]` names are optional password accounts for
   ORCID-less testing only; real participants just sign in with ORCID.
   Credentials land in `credentials.txt`.

3. **Register the runner** with the token printed by bootstrap:

   ```sh
   docker compose exec runner forgejo-runner register --no-interactive \
     --instance http://forgejo:3000 --token <REGISTRATION_TOKEN> \
     --name ci --labels docker:docker://node:20-bookworm
   docker compose restart runner
   ```

4. **Push the canonical book repo** (printed by bootstrap as well):

   ```sh
   git remote add origin https://git.example.org/course/book.git
   git push -u origin main
   ```

## Auth choices

Identity always comes from ORCID (above). For git and the CLI,
participants generate an **application token** after their first ORCID
sign-in (forge *Settings → Applications → Generate token*, repository +
issue read/write scope) and use it over HTTPS; SSH on port 2222 also
works if you prefer keys. Never commit tokens — the `book` CLI reads
them from `~/.config/book/config.toml` or the `BOOK_TOKEN` environment
variable.

## Domains

Prefer subdomains over path prefixes if DNS allows: `git.example.org` →
forgejo:3000, `book.example.org` → nginx:80. The provided `nginx.conf` is
the single-host fallback (book on 8080, Forgejo on 3000). The built site
and diff pages use only relative asset paths, so they work under any
prefix either way.

## Acceptance checklist

- [ ] a person with only an ORCID iD signs in on the forge; an account
      appears with their ORCID iD as username (after the one-time
      email/username confirmation)
- [ ] password sign-in form is absent (unless `FORGEJO_PASSWORD_SIGNIN=true`)
- [ ] the new participant generates an application token, clones over
      HTTPS, cannot push to `main`, can push `username/*` branches
- [ ] opening a PR triggers the `pr-diff` workflow; the diff link appears
      as a PR comment within ~1 min
- [ ] the diff page shows the change's discussion; signed in, replying,
      request-changes, approve and merge all work from that page
- [ ] merging a PR redeploys the book at `/book/`
- [ ] with `[oauth] client_id` in `book.toml`: the site's "Sign in with
      ORCID" button completes the site → forge → ORCID chain without
      pasting a token (needs HTTPS or localhost — the PKCE flow uses
      WebCrypto)
