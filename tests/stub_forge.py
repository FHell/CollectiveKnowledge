#!/usr/bin/env python3
"""A minimal in-process Forgejo API stub backed by a real bare git repo.

Implements just the Gitea-compatible endpoints the `book` CLI and the
in-browser client (forge-client.js) use, so the whole remote workflow —
submit → changes → review/discuss → push-review → request-changes →
approve — can be integration-tested without Docker, from the CLI and
from a real browser (CORS is wide open for that reason).

Auth convention: `Authorization: token <name>` authenticates as user
<name>. No passwords — this is a test double.

Usage: stub_forge.py <port> <bare-repo-path> <owner> <repo>
"""

from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BARE = None
OWNER = "owner"
REPO = "repo"

PRS: dict[int, dict] = {}
COMMENTS: dict[int, list[dict]] = {}
REVIEWS: dict[int, list[dict]] = {}
NEXT_PR = [1]
NEXT_COMMENT = [1]
CLOCK = [0]


def now() -> str:
    # strictly increasing timestamps so thread ordering is deterministic
    CLOCK[0] += 1
    base = datetime.datetime(2026, 1, 1) + datetime.timedelta(minutes=CLOCK[0])
    return base.strftime("%Y-%m-%dT%H:%M:%SZ")


def git(*args, cwd=None):
    res = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    if res.returncode != 0:
        raise RuntimeError(f"git {args} failed: {res.stderr}")
    return res.stdout.strip()


def pr_json(pr: dict) -> dict:
    return {
        "number": pr["number"],
        "title": pr["title"],
        "body": pr["body"],
        "state": pr["state"],
        "user": {"login": pr["user"]},
        "head": {"ref": pr["head"]},
        "base": {"ref": pr["base"]},
        "html_url": f"http://stub/{OWNER}/{REPO}/pulls/{pr['number']}",
        "created_at": pr.get("created_at", "2026-01-01T00:00:00Z"),
        "updated_at": "2026-01-01T00:00:00Z",
        "merged": pr.get("merged", False),
    }


def create_pr(payload: dict, user: str) -> tuple[int, dict]:
    head, base = payload["head"], payload.get("base", "main")
    for pr in PRS.values():
        if pr["head"] == head and pr["state"] == "open":
            return 409, {"message": "pull request already exists"}
    n = NEXT_PR[0]
    NEXT_PR[0] += 1
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


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status: int, data=None):
        body = json.dumps(data).encode() if data is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # wide-open CORS: lets the static site under test (served from a
        # different local port) talk to this stub like a real forge with
        # [cors] enabled
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, Accept")
        self.end_headers()
        self.wfile.write(body)

    def _payload(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def _user(self) -> str:
        auth = self.headers.get("Authorization") or ""
        m = re.match(r"(?:token|Bearer)\s+(\S+)", auth)
        return m.group(1) if m else ""

    def route(self, method: str):
        path = self.path.split("?")[0]

        if method == "GET" and path == "/api/v1/user":
            user = self._user()
            if not user:
                return self._send(401, {"message": "token required"})
            return self._send(200, {"login": user, "id": 1})

        prefix = f"/api/v1/repos/{OWNER}/{REPO}"
        if not path.startswith(prefix):
            return self._send(404, {"message": "unknown repo"})
        sub = path[len(prefix):]

        if method == "GET" and sub == "/pulls":
            state = "open"
            m = re.search(r"state=(\w+)", self.path)
            if m:
                state = m.group(1)
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

        # test-harness introspection endpoint
        if method == "GET" and sub == "/_state":
            return self._send(200, {
                "prs": {k: pr_json(v) for k, v in PRS.items()},
                "reviews": REVIEWS,
                "comments": COMMENTS,
            })
        return self._send(404, {"message": f"unhandled {method} {sub}"})

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def do_PATCH(self):
        self.route("PATCH")

    def do_OPTIONS(self):
        self._send(204)


def main():
    global BARE, OWNER, REPO
    port = int(sys.argv[1])
    BARE = sys.argv[2]
    OWNER, REPO = sys.argv[3], sys.argv[4]
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"stub forge on :{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
