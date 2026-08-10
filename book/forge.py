"""Minimal forge REST API clients: Forgejo/Gitea and GitHub.

Token comes from config or the BOOK_TOKEN environment variable; only the
handful of endpoints the MVP needs are wrapped. `Forge.for_repo()` picks
the right backend from the origin remote's host.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import requests

from . import config


class ForgeError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class Forge:
    def __init__(self, base_url: str, owner: str, repo: str, token: str | None = None):
        self.base = base_url.rstrip("/")
        self.owner = owner
        self.repo = repo
        self.token = token

    @classmethod
    def for_repo(cls, root: Path) -> "Forge":
        base, owner, name = config.remote_coords(root)
        impl = GitHubForge if urlparse(base).netloc == "github.com" else Forge
        return impl(base, owner, name, token=config.token(root))

    # -- plumbing -------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self.base}/api/v1/repos/{self.owner}/{self.repo}{path}"

    def _req(self, method: str, path: str, **kwargs):
        headers = kwargs.pop("headers", {})
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        resp = requests.request(
            method, self._url(path), headers=headers, timeout=30, **kwargs
        )
        if resp.status_code >= 400:
            raise ForgeError(
                f"{method} {path} -> {resp.status_code}: {resp.text[:300]}",
                status=resp.status_code,
            )
        return resp.json() if resp.text else None

    # -- pull requests ----------------------------------------------------

    def create_pr(self, head: str, base: str, title: str, body: str = "") -> dict:
        try:
            return self._req(
                "POST", "/pulls",
                json={"head": head, "base": base, "title": title, "body": body},
            )
        except ForgeError as e:
            if e.status == 409:  # PR for this head already exists
                existing = self.find_pr(head)
                if existing:
                    return existing
            raise

    def find_pr(self, head: str) -> dict | None:
        for pr in self.list_prs("open"):
            if pr.get("head", {}).get("ref") == head:
                return pr
        return None

    def list_prs(self, state: str = "open") -> list[dict]:
        return self._req("GET", f"/pulls?state={state}&limit=50") or []

    def get_pr(self, index: int) -> dict:
        return self._req("GET", f"/pulls/{index}")

    def pr_files(self, index: int) -> list[dict]:
        return self._req("GET", f"/pulls/{index}/files?limit=100") or []

    def merge_pr(self, index: int, style: str = "merge") -> None:
        # merge commit, not squash: squash would collapse authorship and
        # break paragraph-blame provenance
        self._req("POST", f"/pulls/{index}/merge", json={"Do": style})

    def review(self, index: int, event: str, body: str = "") -> dict:
        return self._req(
            "POST", f"/pulls/{index}/reviews", json={"event": event, "body": body}
        )

    # -- issue comments ---------------------------------------------------

    def post_comment(self, index: int, body: str) -> dict:
        return self._req("POST", f"/issues/{index}/comments", json={"body": body})

    def list_comments(self, index: int) -> list[dict]:
        return self._req("GET", f"/issues/{index}/comments") or []

    def edit_comment(self, comment_id: int, body: str) -> dict:
        return self._req("PATCH", f"/issues/comments/{comment_id}", json={"body": body})

    def upsert_comment(self, index: int, marker: str, body: str) -> dict:
        """Create or update a single bot comment identified by a marker.

        Keeps CI from spamming the PR: the rendered-diff link comment is
        edited in place on every push.
        """
        body = f"{marker}\n{body}"
        for comment in self.list_comments(index):
            if marker in (comment.get("body") or ""):
                return self.edit_comment(comment["id"], body)
        return self.post_comment(index, body)


class GitHubForge(Forge):
    """GitHub.com backend — same surface, slightly different endpoints."""

    def _url(self, path: str) -> str:
        return f"https://api.github.com/repos/{self.owner}/{self.repo}{path}"

    def create_pr(self, head: str, base: str, title: str, body: str = "") -> dict:
        try:
            return self._req(
                "POST", "/pulls",
                json={"head": head, "base": base, "title": title, "body": body},
            )
        except ForgeError as e:
            if e.status == 422:  # PR for this head already exists
                existing = self.find_pr(head)
                if existing:
                    return existing
            raise

    def merge_pr(self, index: int, style: str = "merge") -> None:
        self._req("PUT", f"/pulls/{index}/merge", json={"merge_method": style})
