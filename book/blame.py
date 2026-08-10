"""Paragraph-level blame, wrapping `git blame --line-porcelain`.

A paragraph is attributed to the author who wrote the majority of its lines
(ties broken by most recent commit). Paragraph line ranges come from the
doctree (myst records source lines), so the hashes here match the
``data-phash`` values the builder stamps into the HTML.
"""

from __future__ import annotations

import datetime as _dt
from collections import Counter
from pathlib import Path

from .gitutils import GitError, git
from .mystdoc import para_hash, parse, paragraphs_with_lines


def _line_blame(root: Path, relpath: str) -> list[dict]:
    """One dict per line of the working-tree file: author/email/time/sha."""
    out = git("blame", "--line-porcelain", "--", relpath, cwd=root)
    lines: list[dict] = []
    current: dict = {}
    for raw in out.splitlines():
        if raw.startswith("\t"):
            lines.append(dict(current))
            continue
        parts = raw.split(" ", 1)
        key = parts[0]
        val = parts[1] if len(parts) > 1 else ""
        if len(key) == 40 and all(c in "0123456789abcdef" for c in key):
            current["sha"] = key
        elif key == "author":
            current["author"] = val
        elif key == "author-mail":
            current["email"] = val.strip("<>")
        elif key == "author-time":
            current["time"] = int(val)
    return lines


def file_blame(root: Path, relpath: str) -> list[dict]:
    """Blame entries per paragraph: hash, excerpt, author, email, date, commit."""
    root = Path(root)
    text = (root / relpath).read_text()
    doc = parse(text)
    paras = paragraphs_with_lines(doc)
    try:
        lines = _line_blame(root, relpath)
    except GitError:
        lines = []
    total = len(text.splitlines())

    # line range for each paragraph: from its start line to just before the
    # next paragraph's start (myst lines are 1-based)
    starts = [(ln, txt) for ln, txt in paras if ln is not None]
    results = []
    for i, (ln, txt) in enumerate(starts):
        end = starts[i + 1][0] - 1 if i + 1 < len(starts) else total + 1
        chunk = lines[ln - 1 : end - 1] if lines else []
        entry = {
            "hash": para_hash(txt),
            "excerpt": txt[:80],
            "author": "",
            "email": "",
            "date": "",
            "commit": "",
        }
        authored = [l for l in chunk if l.get("author")]
        if authored:
            counts = Counter(l["author"] for l in authored)
            top_author, _ = counts.most_common(1)[0]
            own = [l for l in authored if l["author"] == top_author]
            latest = max(own, key=lambda l: l.get("time", 0))
            entry.update(
                author=top_author,
                email=latest.get("email", ""),
                commit=latest.get("sha", ""),
                date=_dt.datetime.fromtimestamp(
                    latest.get("time", 0), tz=_dt.timezone.utc
                ).strftime("%Y-%m-%d"),
            )
        results.append(entry)
    return results


def print_blame(root: Path, relpath: str) -> None:
    for e in file_blame(root, relpath):
        author = e["author"] or "(uncommitted)"
        print(f"{e['commit'][:8] or '-' * 8}  {author:<20} {e['date']:<10}  {e['excerpt']}")
