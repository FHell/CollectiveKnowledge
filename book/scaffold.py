"""`book init` — scaffold a new book repository."""

from __future__ import annotations

from pathlib import Path

from .gitutils import git

BOOK_TOML = """\
[book]
title = "{title}"

[site]
# Optional: where the built book / rendered diffs are published.
# Used only for printing helpful URLs; CI owns actual deployment.
# base_url = "https://book.example.org"
# diffs_url = "https://book.example.org/diffs"
"""

MYST_YML = """\
version: 1
project:
  title: {title}
"""

TOC_YML = """\
format: book
chapters:
  - file: chapters/01-introduction.md
"""

FIRST_CHAPTER = """\
# Introduction

Welcome to *{title}*. This paragraph is the first piece of collective
knowledge in this book; edit it, or add new chapters under `chapters/`.

Mathematics is typeset with dollar math, for example $e^{{i\\pi}} + 1 = 0$.
"""

VOUCHES_YAML = "vouches: []\n"

GITIGNORE = """\
_build/
.book/
__pycache__/
"""


def init(path: Path, title: str = "Untitled Book") -> Path:
    root = Path(path).resolve()
    if (root / "book.toml").exists():
        raise FileExistsError(f"{root} already contains a book (book.toml exists)")
    (root / "chapters").mkdir(parents=True, exist_ok=True)
    (root / "meta").mkdir(parents=True, exist_ok=True)

    (root / "book.toml").write_text(BOOK_TOML.format(title=title))
    (root / "myst.yml").write_text(MYST_YML.format(title=title))
    (root / "_toc.yml").write_text(TOC_YML)
    (root / "chapters" / "01-introduction.md").write_text(
        FIRST_CHAPTER.format(title=title)
    )
    (root / "meta" / "vouches.yaml").write_text(VOUCHES_YAML)
    (root / ".gitignore").write_text(GITIGNORE)

    if not (root / ".git").exists():
        git("init", "-b", "main", cwd=root)
    git("add", "-A", cwd=root)
    git("commit", "-m", f"book init: {title}", cwd=root)
    return root
