#!/usr/bin/env python3
"""A minimal in-process Forgejo API stub backed by a real bare git repo.

Implements the Gitea-compatible endpoints the `book` CLI and the
in-browser client (forge-client.js) use, so the whole remote workflow —
submit → changes → review/discuss → push-review → request-changes →
approve, plus the web verbs (edit / vouch / discuss) via the contents
API — can be integration-tested and demoed without Docker, from the CLI
and from a real browser (CORS is wide open for that reason).

It also mocks the production auth chain
    site → forge (OAuth2 + PKCE) → ORCID
in one hop: /login/oauth/authorize shows a picker of fictional ORCID
personas instead of bouncing to orcid.org, then issues a code and honors
the standard PKCE token exchange. The access token it returns is simply
the persona's ORCID iD.

Auth convention everywhere: `Authorization: token <name>` authenticates
as user <name>. No passwords — this is a test/demo double.

Usage: stub_forge.py <port> <bare-repo-path> <owner> <repo>
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import html
import json
import pathlib
import re
import secrets
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

BARE = None
OWNER = "owner"
REPO = "repo"
PORT = 0

PRS: dict[int, dict] = {}
ISSUES: dict[int, dict] = {}
COMMENTS: dict[int, list[dict]] = {}
REVIEWS: dict[int, list[dict]] = {}
NEXT_INDEX = [1]  # PRs and issues share one number space, like Gitea
NEXT_COMMENT = [1]
CLOCK = [0]

# The mock identity provider: fictional researchers with ORCID-style iDs
# (Josiah Carberry is ORCID's official fictitious example researcher).
PERSONAS = {
    "0000-0002-1825-0097": "Josiah Carberry",
    "0000-0001-0000-0042": "Ada Demo",
    "0000-0003-0000-0007": "Grace Example",
}
OAUTH_CODES: dict[str, dict] = {}


def now() -> str:
    # strictly increasing timestamps so thread ordering is deterministic
    CLOCK[0] += 1
    base = datetime.datetime(2026, 1, 1) + datetime.timedelta(minutes=CLOCK[0])
    return base.strftime("%Y-%m-%dT%H:%M:%SZ")


def git(*args, cwd=None, input=None):
    res = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, input=input
    )
    if res.returncode != 0:
        raise RuntimeError(f"git {args} failed: {res.stderr}")
    return res.stdout.strip()


def take_index() -> int:
    n = NEXT_INDEX[0]
    NEXT_INDEX[0] += 1
    return n


def html_url(kind: str, n: int) -> str:
    return f"http://127.0.0.1:{PORT}/{OWNER}/{REPO}/{kind}/{n}"


# --- pull requests -----------------------------------------------------------

def pr_json(pr: dict) -> dict:
    return {
        "number": pr["number"],
        "title": pr["title"],
        "body": pr["body"],
        "state": pr["state"],
        "user": {"login": pr["user"]},
        "head": {"ref": pr["head"]},
        "base": {"ref": pr["base"]},
        "html_url": html_url("pulls", pr["number"]),
        "created_at": pr.get("created_at", "2026-01-01T00:00:00Z"),
        "updated_at": "2026-01-01T00:00:00Z",
        "merged": pr.get("merged", False),
    }


def create_pr(payload: dict, user: str) -> tuple[int, dict]:
    head, base = payload["head"], payload.get("base", "main")
    for pr in PRS.values():
        if pr["head"] == head and pr["state"] == "open":
            return 409, {"message": "pull request already exists"}
    n = take_index()
    PRS[n] = {
        "number": n,
        "title": payload.get("title", head),
        "body": payload.get("body", ""),
        "state": "open",
        "user": user or head.split("/")[0],
        "head": head,
        "base": base,
        "created_at": now(),
    }
    # expose the Gitea-compatible pull ref for `git fetch refs/pull/<n>/head`
    sha = git("rev-parse", f"refs/heads/{head}", cwd=BARE)
    git("update-ref", f"refs/pull/{n}/head", sha, cwd=BARE)
    # remember the base tip so /files stays correct even after the merge
    PRS[n]["base_sha"] = git("rev-parse", f"refs/heads/{base}", cwd=BARE)
    return 201, pr_json(PRS[n])


def merge_pr(n: int) -> tuple[int, dict]:
    pr = PRS[n]
    with tempfile.TemporaryDirectory() as tmp:
        git("clone", BARE, tmp)
        git("config", "user.name", "Forge Stub", cwd=tmp)
        git("config", "user.email", "stub@example.org", cwd=tmp)
        git("checkout", pr["base"], cwd=tmp)
        git(
            "merge", "--no-ff", f"origin/{pr['head']}",
            "-m", f"Merge pull request #{n}: {pr['title']}", cwd=tmp,
        )
        git("push", "origin", pr["base"], cwd=tmp)
    pr["state"] = "closed"
    pr["merged"] = True
    return 200, {}


def pr_files(n: int) -> list[dict]:
    pr = PRS[n]
    base = pr.get("base_sha", pr["base"])
    names = git(
        "diff", "--name-only", f"{base}...refs/heads/{pr['head']}", cwd=BARE
    ).splitlines()
    return [{"filename": f} for f in names]


# --- issues ------------------------------------------------------------------

def issue_json(i: dict) -> dict:
    return {
        "number": i["number"],
        "title": i["title"],
        "body": i["body"],
        "state": i["state"],
        "user": {"login": i["user"]},
        "html_url": html_url("issues", i["number"]),
        "created_at": i["created_at"],
    }


def create_issue(payload: dict, user: str) -> tuple[int, dict]:
    n = take_index()
    ISSUES[n] = {
        "number": n,
        "title": payload.get("title", f"issue {n}"),
        "body": payload.get("body", ""),
        "state": "open",
        "user": user or "?",
        "created_at": now(),
    }
    return 201, issue_json(ISSUES[n])


# --- contents API (web edit + vouch flows) ------------------------------------

def blob_sha(ref: str, path: str) -> str | None:
    try:
        return git("rev-parse", f"{ref}:{path}", cwd=BARE)
    except RuntimeError:
        return None


def get_contents(path: str, ref: str) -> tuple[int, dict]:
    sha = blob_sha(ref, path)
    if sha is None:
        return 404, {"message": f"no {path} at {ref}"}
    raw = subprocess.run(
        ["git", "show", f"{ref}:{path}"], cwd=BARE, capture_output=True
    ).stdout
    return 200, {
        "path": path,
        "sha": sha,
        "content": base64.b64encode(raw).decode(),
        "encoding": "base64",
    }


def put_contents(path: str, payload: dict, user: str) -> tuple[int, dict]:
    branch = payload.get("branch", "main")
    current = blob_sha(f"refs/heads/{branch}", path)
    if current and payload.get("sha") and payload["sha"] != current:
        return 409, {"message": "sha mismatch: file changed since you read it"}
    content = base64.b64decode(payload.get("content", ""))
    author = user or "web"
    with tempfile.TemporaryDirectory() as tmp:
        git("clone", "--branch", branch, BARE, tmp)
        git("config", "user.name", author, cwd=tmp)
        git("config", "user.email", f"{author}@demo.example", cwd=tmp)
        target = pathlib.Path(tmp) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        git("add", path, cwd=tmp)
        git("commit", "-m", payload.get("message", f"edit {path}"), cwd=tmp)
        git("push", "origin", branch, cwd=tmp)
    return 201, {"content": {"path": path, "sha": blob_sha(f"refs/heads/{branch}", path)}}


def create_branch(payload: dict) -> tuple[int, dict]:
    new, old = payload["new_branch_name"], payload.get("old_branch_name", "main")
    sha = git("rev-parse", f"refs/heads/{old}", cwd=BARE)
    git("update-ref", f"refs/heads/{new}", sha, cwd=BARE)
    return 201, {"name": new}


# --- mock OAuth (the ORCID chain, in one hop) ----------------------------------

def b64url_sha256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def authorize_page(params: dict) -> str:
    redirect = params.get("redirect_uri", [""])[0]
    state = params.get("state", [""])[0]
    challenge = params.get("code_challenge", [""])[0]
    qs = (f"redirect_uri={quote(redirect, safe='')}&state={quote(state, safe='')}"
          f"&code_challenge={quote(challenge, safe='')}")
    rows = "".join(
        f'<p><a href="/login/oauth/pick?user={quote(pid)}&{qs}">'
        f"<strong>{html.escape(name)}</strong> &middot; "
        f"<code>{html.escape(pid)}</code></a></p>"
        for pid, name in PERSONAS.items()
    )
    return f"""<!DOCTYPE html><html><head><title>Mock ORCID sign-in</title>
<style>body{{font-family:system-ui,sans-serif;max-width:34rem;margin:4rem auto;
padding:0 1rem}}a{{text-decoration:none;color:#1c4b82;display:block;
border:1px solid #ddd;border-radius:8px;padding:.7rem 1rem}}
a:hover{{background:#f4f1e8}}</style></head><body>
<h1>Sign in (demo)</h1>
<p>This is the <em>mock</em> of the ORCID sign-in step — in production
you would authenticate at orcid.org. Pick a persona:</p>
{rows}
<p style="color:#777;font-size:.85rem">The persona's ORCID iD becomes
your username, exactly as in the real deployment.</p>
</body></html>"""


def oauth_pick(params: dict) -> tuple[str, str]:
    """-> (Location header value, code)."""
    user = params.get("user", [""])[0]
    redirect = params.get("redirect_uri", [""])[0]
    state = params.get("state", [""])[0]
    code = secrets.token_urlsafe(16)
    OAUTH_CODES[code] = {
        "user": user,
        "challenge": params.get("code_challenge", [""])[0],
    }
    sep = "&" if "?" in redirect else "?"
    return f"{redirect}{sep}code={quote(code)}&state={quote(state)}", code


def oauth_token(payload: dict) -> tuple[int, dict]:
    rec = OAUTH_CODES.pop(payload.get("code", ""), None)
    if rec is None:
        return 400, {"error": "invalid_grant", "error_description": "unknown code"}
    if rec["challenge"]:
        verifier = payload.get("code_verifier", "")
        if b64url_sha256(verifier) != rec["challenge"]:
            return 400, {"error": "invalid_grant",
                         "error_description": "PKCE verification failed"}
    return 200, {
        "access_token": rec["user"],
        "token_type": "bearer",
        "expires_in": 3600,
    }


# --- read-only HTML views (so forge links in the demo aren't dead) --------------

def thread_html(kind: str, n: int) -> str | None:
    if kind == "pulls" and n in PRS:
        head = PRS[n]
        badge = "merged" if head.get("merged") else head["state"]
    elif kind == "issues" and n in ISSUES:
        head = ISSUES[n]
        badge = head["state"]
    else:
        return None
    items = [(head["user"], head.get("created_at", ""), head["body"], "")]
    for c in COMMENTS.get(n, []):
        items.append((c["user"]["login"], c["created_at"], c["body"], ""))
    for r in REVIEWS.get(n, []):
        items.append((r["user"]["login"], r["submitted_at"], r["body"], r["state"]))
    items.sort(key=lambda t: t[1])
    rows = "".join(
        f'<div class="c"><b>{html.escape(u)}</b>'
        + (f' <span class="s">{html.escape(s)}</span>' if s else "")
        + f' <span class="d">{html.escape(d[:16].replace("T", " "))}</span>'
        f"<pre>{html.escape(b)}</pre></div>"
        for u, d, b, s in items
    )
    return f"""<!DOCTYPE html><html><head>
<title>#{n} {html.escape(head["title"])}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:44rem;margin:2rem auto;
padding:0 1rem}}.c{{border:1px solid #ddd;border-radius:8px;padding:.5rem .8rem;
margin:.6rem 0}}.d{{color:#999;font-size:.8rem}}.s{{background:#eee;
border-radius:99px;padding:0 .5rem;font-size:.78rem}}
pre{{white-space:pre-wrap;font-family:inherit;margin:.3rem 0 0}}</style>
</head><body>
<h1>#{n} {html.escape(head["title"])} <small>[{badge}]</small></h1>
<p style="color:#777">Read-only stub view of the forge — the demo's
interactive surface is the published site.</p>
{rows}</body></html>"""


# --- HTTP plumbing -------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _headers(self, status: int, ctype: str, length: int, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        # wide-open CORS: lets the static site under test (served from a
        # different local port) talk to this stub like a real forge with
        # [cors] enabled
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, Accept")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def _send(self, status: int, data=None):
        body = json.dumps(data).encode() if data is not None else b""
        self._headers(status, "application/json", len(body))
        self.wfile.write(body)

    def _send_html(self, status: int, text: str):
        body = text.encode()
        self._headers(status, "text/html; charset=utf-8", len(body))
        self.wfile.write(body)

    def _payload(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def _user(self) -> str:
        auth = self.headers.get("Authorization") or ""
        m = re.match(r"(?:token|Bearer)\s+(\S+)", auth)
        return m.group(1) if m else ""

    def route(self, method: str):
        url = urlparse(self.path)
        path, params = url.path, parse_qs(url.query)

        # ---- mock OAuth (mimics forge-mediated ORCID sign-in) ----------
        if method == "GET" and path == "/login/oauth/authorize":
            return self._send_html(200, authorize_page(params))
        if method == "GET" and path == "/login/oauth/pick":
            location, _ = oauth_pick(params)
            body = b"redirecting"
            self._headers(302, "text/plain", len(body), {"Location": location})
            return self.wfile.write(body)
        if method == "POST" and path == "/login/oauth/access_token":
            return self._send(*oauth_token(self._payload()))

        # ---- read-only HTML thread views -------------------------------
        m = re.match(rf"^/{OWNER}/{REPO}/(pulls|issues)/(\d+)$", path)
        if m and method == "GET":
            page = thread_html(m.group(1), int(m.group(2)))
            if page is None:
                return self._send_html(404, "<h1>not found</h1>")
            return self._send_html(200, page)

        if method == "GET" and path == "/api/v1/user":
            user = self._user()
            if not user:
                return self._send(401, {"message": "token required"})
            return self._send(200, {
                "login": user, "id": 1,
                "full_name": PERSONAS.get(user, ""),
            })

        prefix = f"/api/v1/repos/{OWNER}/{REPO}"
        if not path.startswith(prefix):
            return self._send(404, {"message": "unknown route"})
        sub = path[len(prefix):]

        if method == "GET" and sub == "/pulls":
            state = (params.get("state") or ["open"])[0]
            prs = [
                pr_json(p) for p in PRS.values()
                if state == "all" or p["state"] == state
            ]
            return self._send(200, prs)
        if method == "POST" and sub == "/pulls":
            return self._send(*create_pr(self._payload(), self._user()))

        m = re.match(r"^/pulls/(\d+)(/.*)?$", sub)
        if m:
            n, rest = int(m.group(1)), m.group(2) or ""
            if n not in PRS:
                return self._send(404, {"message": "no such PR"})
            if method == "GET" and rest == "":
                return self._send(200, pr_json(PRS[n]))
            if method == "GET" and rest == "/files":
                return self._send(200, pr_files(n))
            if method == "POST" and rest == "/merge":
                return self._send(*merge_pr(n))
            if method == "GET" and rest == "/reviews":
                return self._send(200, REVIEWS.get(n, []))
            if method == "POST" and rest == "/reviews":
                p = self._payload()
                r = {
                    "id": len(REVIEWS.get(n, [])) + 1,
                    "user": {"login": self._user() or "?"},
                    "state": p.get("event", "COMMENT"),
                    "body": p.get("body", ""),
                    "submitted_at": now(),
                }
                REVIEWS.setdefault(n, []).append(r)
                return self._send(200, r)

        if sub == "/issues" and method == "POST":
            return self._send(*create_issue(self._payload(), self._user()))
        if sub == "/issues" and method == "GET":
            q = (params.get("q") or [""])[0]
            out = [
                issue_json(i) for i in ISSUES.values()
                if not q or q in i["title"] or q in i["body"]
            ]
            return self._send(200, out)

        m = re.match(r"^/issues/(\d+)/comments$", sub)
        if m:
            n = int(m.group(1))
            if method == "GET":
                return self._send(200, COMMENTS.get(n, []))
            if method == "POST":
                c = {
                    "id": NEXT_COMMENT[0],
                    "user": {"login": self._user() or "?"},
                    "body": self._payload()["body"],
                    "created_at": now(),
                }
                NEXT_COMMENT[0] += 1
                COMMENTS.setdefault(n, []).append(c)
                return self._send(201, c)

        m = re.match(r"^/issues/comments/(\d+)$", sub)
        if m and method == "PATCH":
            cid = int(m.group(1))
            for clist in COMMENTS.values():
                for c in clist:
                    if c["id"] == cid:
                        c["body"] = self._payload()["body"]
                        return self._send(200, c)
            return self._send(404, {"message": "no such comment"})

        m = re.match(r"^/contents/(.+)$", sub)
        if m:
            file_path = m.group(1)
            if method == "GET":
                ref = (params.get("ref") or ["main"])[0]
                return self._send(*get_contents(file_path, ref))
            if method == "PUT":
                return self._send(*put_contents(file_path, self._payload(), self._user()))

        if sub == "/branches" and method == "POST":
            return self._send(*create_branch(self._payload()))

        # test-harness introspection endpoint
        if method == "GET" and sub == "/_state":
            return self._send(200, {
                "prs": {k: pr_json(v) for k, v in PRS.items()},
                "issues": {k: issue_json(v) for k, v in ISSUES.items()},
                "reviews": REVIEWS,
                "comments": COMMENTS,
            })
        return self._send(404, {"message": f"unhandled {method} {sub}"})

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_PUT(self):
        self.route("PUT")

    def do_PATCH(self):
        self.route("PATCH")

    def do_OPTIONS(self):
        self._send(204)


def main():
    global BARE, OWNER, REPO, PORT
    PORT = int(sys.argv[1])
    BARE = sys.argv[2]
    OWNER, REPO = sys.argv[3], sys.argv[4]
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"stub forge on :{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
