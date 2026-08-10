# Infrastructure

One host, three containers (see `docker-compose.yml`):

| Service | Role | Port |
|---|---|---|
| forgejo | repo hosting, users, PRs, Actions | 3000 (HTTP), 2222 (SSH) |
| runner  | executes `.forgejo/workflows/` | — |
| nginx   | serves built book at `/`, diffs at `/diffs/` | 8080 |

The only glue between CI and the web server is the shared `book-site`
volume: the deploy workflow writes the built site to `/site/book`, the PR
workflow writes rendered diffs to `/site/diffs/pr-<n>/`, and nginx serves
both read-only.

## Setup

1. **Start services**

   ```sh
   cd infra
   FORGEJO_ROOT_URL=https://git.example.org/ docker compose up -d
   ```

   For a local test run, plain `docker compose up -d` works
   (Forgejo on `http://localhost:3000`, book on `http://localhost:8080`).

2. **Bootstrap accounts, repo, branch protection, tokens**

   ```sh
   ./bootstrap.sh frank course book alice bob carol
   ```

   Creates the instructor admin (`frank`), org `course`, repo
   `course/book`, protects `main` (PRs only; instructor may push — do NOT
   restrict branch creation, students need `<username>/*`), one account +
   API token per student, and the `CI_TOKEN` secret / `SITE_URL` variable
   the workflows use. Credentials land in `credentials.txt`.

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

HTTPS + token is the documented default for students (simplest to
support); SSH on port 2222 also works if you prefer keys. Never commit
tokens — the `book` CLI reads them from `~/.config/book/config.toml` or
the `BOOK_TOKEN` environment variable.

## Domains

Prefer subdomains over path prefixes if DNS allows: `git.example.org` →
forgejo:3000, `book.example.org` → nginx:80. The provided `nginx.conf` is
the single-host fallback (book on 8080, Forgejo on 3000). The built site
and diff pages use only relative asset paths, so they work under any
prefix either way.

## Acceptance checklist (Phase 1)

- [ ] student can clone over HTTPS with token
- [ ] student `git push origin main` is rejected
- [ ] student can push `username/*` branches
- [ ] opening a PR triggers the `pr-diff` workflow; the diff link appears
      as a PR comment within ~1 min
- [ ] merging a PR redeploys the book at `/`
