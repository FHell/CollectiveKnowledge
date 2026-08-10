"""Local change management: namespaced branches, save, log.

Students never need raw git: `book change new` makes a `<username>/<slug>`
branch, `book save` is add+commit with an auto-message, `book submit`
(remote.py) pushes and opens the PR.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import config
from .gitutils import current_branch, git, user_identity


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "change"


def branch_user(root: Path) -> str:
    """The namespace for this user's branches: config user, else git name."""
    name = config.username(root)
    if name:
        return name
    return _slug(user_identity(root)[0])


def change_new(root: Path, description: str) -> str:
    branch = f"{branch_user(root)}/{_slug(description)}"
    git("checkout", "-b", branch, cwd=root)
    return branch


def change_list_local(root: Path) -> list[dict]:
    out = git(
        "for-each-ref", "refs/heads", "--format=%(refname:short)\t%(committerdate:short)",
        cwd=root,
    )
    branches = []
    cur = current_branch(root)
    for line in out.splitlines():
        name, date = line.split("\t")
        if "/" not in name:
            continue  # only namespaced change branches
        branches.append({"name": name, "date": date, "current": name == cur})
    return branches


def change_switch(root: Path, name: str) -> str:
    if "/" not in name:
        name = f"{branch_user(root)}/{name}"
    git("checkout", name, cwd=root)
    return name


def save(root: Path, message: str | None = None) -> str:
    git("add", "-A", cwd=root)
    staged = git("diff", "--cached", "--name-only", cwd=root)
    if not staged:
        return ""
    if not message:
        files = staged.splitlines()
        shown = ", ".join(Path(f).name for f in files[:3])
        more = f" (+{len(files) - 3} more)" if len(files) > 3 else ""
        message = f"Update {shown}{more}"
    git("commit", "-m", message, cwd=root)
    return git("rev-parse", "--short", "HEAD", cwd=root)


def log(root: Path, limit: int = 20) -> str:
    return git(
        "log", f"-{limit}", "--pretty=format:%C(yellow)%h%Creset %C(cyan)%an%Creset %s %C(dim white)(%ar)%Creset",
        "--color=always", cwd=root,
    )
