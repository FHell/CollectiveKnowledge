"""Small helpers around shelling out to git.

All git interaction in the tool goes through :func:`git` so there is a
single place to observe/patch it (Phase 0 requirement: know where git is
shelled out).
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def git(*args: str, cwd: Path | str | None = None, check: bool = True) -> str:
    """Run a git command and return stripped stdout."""
    res = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True
    )
    if check and res.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed (exit {res.returncode}):\n"
            f"{res.stderr.strip() or res.stdout.strip()}"
        )
    return (res.stdout or "").strip()


def repo_root(start: Path | str | None = None) -> Path:
    """Find the enclosing book repository (marked by book.toml)."""
    path = Path(start or Path.cwd()).resolve()
    for p in [path, *path.parents]:
        if (p / "book.toml").exists():
            return p
    raise GitError("not inside a book repository (no book.toml found)")


def current_branch(cwd: Path | str) -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)


def file_at_ref(cwd: Path | str, ref: str, relpath: str) -> str | None:
    """Content of a file at a git ref, or None if it does not exist there."""
    res = subprocess.run(
        ["git", "show", f"{ref}:{relpath}"], cwd=cwd, text=True, capture_output=True
    )
    if res.returncode != 0:
        return None
    return res.stdout


def ls_tree_md(cwd: Path | str, ref: str, subdir: str = "chapters") -> list[str]:
    """Markdown files under subdir/ at a ref."""
    res = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", ref, "--", subdir],
        cwd=cwd, text=True, capture_output=True,
    )
    if res.returncode != 0:
        return []
    return [l for l in res.stdout.splitlines() if l.endswith(".md")]


def user_identity(cwd: Path | str | None = None) -> tuple[str, str]:
    name = git("config", "user.name", cwd=cwd, check=False) or "unknown"
    email = git("config", "user.email", cwd=cwd, check=False) or ""
    return name, email
