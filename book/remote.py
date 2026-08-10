"""Remote workflow commands: clone, submit, changes, review, approve, …

Thin layer over git + the Forgejo REST API. Nothing here modifies Forgejo
itself; PRs are the changes, PR comments are the discussion, and vouches
stay committed in meta/ (metadata in git).
"""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

from . import config
from .changes import branch_user, save as save_commit
from .diff import render_diff
from .forge import Forge, ForgeError
from .gitutils import GitError, current_branch, git
from .vouch import vouch_files


def _say(msg: str) -> None:
    print(msg)


# --- clone -------------------------------------------------------------

def clone(url: str, dest: str | None = None, user: str | None = None) -> Path:
    base, owner, repo = config.parse_remote_url(url)
    target = Path(dest or repo).resolve()
    git("clone", url, str(target))

    if not user:
        user = config.username() or ""
    if not user and sys.stdin.isatty():
        user = input("Your Forgejo username: ").strip()
    if user:
        # fetch only main and this user's own branches — other students'
        # in-progress branches stay out of the local repo (PRs are fetched
        # explicitly via refs/pull/<n>/head during review)
        git("config", "remote.origin.fetch",
            "+refs/heads/main:refs/remotes/origin/main", cwd=target)
        git("config", "--add", "remote.origin.fetch",
            f"+refs/heads/{user}/*:refs/remotes/origin/{user}/*", cwd=target)
        config.write_local_config(target, {"user": {"name": user}})
    forgejo_cfg = {"owner": owner, "repo": repo}
    if base:
        forgejo_cfg["url"] = base
    config.write_local_config(target, {"forgejo": forgejo_cfg})
    return target


# --- submit ------------------------------------------------------------

def _diff_url(root: Path, pr_number: int) -> str | None:
    import tomllib

    try:
        site = tomllib.loads((root / "book.toml").read_text()).get("site", {})
        diffs = site.get("diffs_url")
        if diffs:
            return f"{diffs.rstrip('/')}/pr-{pr_number}/"
    except FileNotFoundError:
        pass
    return None


def submit(root: Path, title: str | None = None) -> dict:
    branch = current_branch(root)
    me = branch_user(root)
    if not branch.startswith(f"{me}/"):
        raise GitError(
            f"you are on '{branch}', not one of your change branches.\n"
            f"Start one with:  book change new \"describe-your-change\""
        )
    git("push", "-u", "origin", branch, cwd=root)

    forge = Forge.for_repo(root)
    pr = forge.find_pr(branch)
    if pr is None:
        if not title:
            title = git("log", "-1", "--pretty=%s", cwd=root)
        body = git("log", "origin/main..HEAD", "--pretty=- %s", cwd=root, check=False)
        pr = forge.create_pr(head=branch, base="main", title=title, body=body)
        _say(f"Opened change #{pr['number']}: {pr['title']}")
    else:
        _say(f"Updated change #{pr['number']}: {pr['title']}")
    _say(f"  PR:   {pr.get('html_url', '')}")
    diff_url = _diff_url(root, pr["number"])
    if diff_url:
        _say(f"  Diff: {diff_url}  (appears once CI finishes)")
    return pr


# --- changes (remote listing) -------------------------------------------

def list_changes(root: Path, state: str = "open") -> list[dict]:
    forge = Forge.for_repo(root)
    return forge.list_prs(state)


def print_changes(prs: list[dict]) -> None:
    if not prs:
        print("No open changes.")
        return
    print(f"{'#':>4}  {'author':<16} {'updated':<12} {'state':<7} title")
    for pr in prs:
        user = (pr.get("user") or {}).get("login", "?")
        updated = (pr.get("updated_at") or "")[:10]
        print(
            f"{pr['number']:>4}  {user:<16} {updated:<12} {pr.get('state', ''):<7} {pr.get('title', '')}"
        )


# --- review --------------------------------------------------------------

def review(root: Path, number: int, open_browser: bool = True) -> Path:
    branch = f"review/pr-{number}"
    git("fetch", "origin", "main", cwd=root)
    try:
        # Forgejo exposes Gitea-compatible refs/pull/<n>/head
        git("fetch", "origin", f"+refs/pull/{number}/head:refs/heads/{branch}",
            cwd=root)
    except GitError:
        # fall back to fetching the head branch named in the PR
        forge = Forge.for_repo(root)
        pr = forge.get_pr(number)
        head_ref = pr["head"]["ref"]
        git("fetch", "origin", f"+refs/heads/{head_ref}:refs/heads/{branch}",
            cwd=root)
    git("checkout", branch, cwd=root)
    out = render_diff(
        root,
        "origin/main",
        None,  # working tree == PR head (and any local edits you make)
        out_path=root / "_build" / f"diff-pr-{number}.html",
        title=f"Change #{number} vs main",
    )
    _say(f"Rendered diff: {out}")
    _say(f"You are now on '{branch}'. Edit files and `book save` if needed,")
    _say(f"then `book push-review {number}` to push your edits to the change.")
    if open_browser:
        webbrowser.open(out.as_uri())
    return out


def push_review(root: Path, number: int) -> None:
    forge = Forge.for_repo(root)
    pr = forge.get_pr(number)
    head_ref = pr["head"]["ref"]
    try:
        git("push", "origin", f"HEAD:refs/heads/{head_ref}", cwd=root)
        _say(f"Pushed your edits to '{head_ref}' (change #{number}).")
    except GitError:
        # No write access to the student's branch: push a maintainer branch
        # and note it on the PR instead.
        me = branch_user(root)
        alt = f"{me}/pr-{number}-edits"
        git("push", "-u", "origin", f"HEAD:refs/heads/{alt}", cwd=root)
        forge.post_comment(
            number,
            f"I could not push to `{head_ref}` directly; my suggested edits are "
            f"on branch `{alt}`. Please merge them into your change.",
        )
        _say(f"No write access to '{head_ref}'; pushed '{alt}' and noted it on the PR.")


# --- request changes / approve -------------------------------------------

def request_changes(root: Path, number: int, message: str) -> None:
    forge = Forge.for_repo(root)
    forge.review(number, "REQUEST_CHANGES", message)
    _say(f"Requested changes on #{number}.")


def approve(
    root: Path,
    number: int,
    vouch: bool = False,
    note: str | None = None,
) -> None:
    forge = Forge.for_repo(root)
    pr = forge.get_pr(number)

    forge.merge_pr(number, style="merge")
    _say(f"Merged change #{number}: {pr.get('title', '')}")

    git("checkout", "main", cwd=root)
    git("pull", "origin", "main", cwd=root)

    if vouch:
        # Vouch *after* the merge and pull, on the merged content, so the
        # paragraph hashes match what is now on main.
        try:
            files = [f["filename"] for f in forge.pr_files(number)]
        except ForgeError:
            files = git(
                "diff", "--name-only", "HEAD^1", "HEAD", cwd=root, check=False
            ).splitlines()
        chapters = [f for f in files if f.startswith("chapters/") and f.endswith(".md")
                    and (Path(root) / f).exists()]
        if chapters:
            n = vouch_files(root, chapters, note=note)
            git("push", "origin", "main", cwd=root)
            _say(f"Vouched for {n} paragraph(s) in {', '.join(chapters)} and pushed.")
        else:
            _say("No chapter files in this change; nothing to vouch for.")
