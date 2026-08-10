# OAuth token-exchange worker

The one tiny server-side piece of the system: a Cloudflare Worker
(free tier) that swaps an OAuth authorization code for an access token,
because GitHub's and ORCID's token endpoints require a client secret
and are not CORS-enabled. It stores nothing; the token goes straight
back to the visitor's browser.

Everything else stays as it is — static site, GitHub API, git as the
database.

## One-time setup (~3 minutes)

**1. Register the GitHub OAuth app** — https://github.com/settings/applications/new

| Field | Value |
|---|---|
| Application name | Collective Knowledge |
| Homepage URL | `https://fhell.github.io/CollectiveKnowledge/` |
| Authorization callback URL | `https://fhell.github.io/CollectiveKnowledge/` |

Note the **Client ID**; generate and note a **Client secret**.

**2. Deploy the worker** (from a machine with Node, or the Cloudflare
dashboard's paste-a-worker editor works too):

```sh
cd worker
# put your Client ID into wrangler.toml (GITHUB_CLIENT_ID = "...")
npx wrangler login          # opens browser, authorizes your CF account
npx wrangler deploy
npx wrangler secret put GITHUB_CLIENT_SECRET   # paste the secret
```

Note the printed worker URL, e.g.
`https://collective-knowledge-oauth.<account>.workers.dev`.

**3. Point the site at it** — in `book.toml` at the repo root:

```toml
[oauth]
client_id = "<Client ID>"
exchange_url = "https://collective-knowledge-oauth.<account>.workers.dev/exchange"
```

Push to `main`. The next Pages deploy adds a **“Sign in with GitHub”**
button to the site's sign-in dialog; the paste-a-token path keeps
working as a fallback.

## Flow

1. Site → `github.com/login/oauth/authorize` (client id is public;
   `state` kept in sessionStorage).
2. GitHub redirects back to the site with `?code=…`.
3. Site POSTs the code to this worker's `/exchange`; the worker adds the
   client secret, calls GitHub's token endpoint, and returns the token.
4. The browser stores the token exactly as if it had been pasted.

The worker only answers to origins in `ALLOWED_ORIGINS`.

## ORCID (planned)

`/orcid/exchange` is already implemented — register an ORCID public API
client (https://orcid.org/developer-tools, redirect URI = the site URL),
set `ORCID_CLIENT_ID` + `ORCID_CLIENT_SECRET` on the worker, and the
site can then obtain the visitor's authenticated ORCID iD and name.
Frontend integration (recording the ORCID iD alongside vouches, and
pairing it with a GitHub identity for write access) is future work —
note that ORCID authenticates *identity* only; writing to the
repository will still go through GitHub.
