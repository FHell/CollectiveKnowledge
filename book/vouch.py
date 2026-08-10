"""`book vouch` — record content-addressed endorsements in meta/vouches.yaml.

Vouches are keyed by paragraph content hash, so they stay attached to the
exact text that was vouched for and go stale naturally when it changes.
They live in git (committed to meta/), not in the forge.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import yaml
from docutils import nodes

from .gitutils import git, user_identity
from .mystdoc import para_hash, parse


def _load(root: Path) -> dict:
    path = root / "meta" / "vouches.yaml"
    if path.exists():
        return yaml.safe_load(path.read_text()) or {"vouches": []}
    return {"vouches": []}


def _save(root: Path, data: dict) -> Path:
    path = root / "meta" / "vouches.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    return path


def vouch_files(
    root: Path,
    relpaths: list[str],
    note: str | None = None,
    paragraph: int | None = None,
    commit: bool = True,
) -> int:
    """Vouch for all paragraphs (or one, 1-based) of the given chapter files.

    Returns the number of vouch records written. Re-vouching the same
    (file, hash, voucher) replaces the previous record.
    """
    root = Path(root)
    name, email = user_identity(root)
    head = git("rev-parse", "HEAD", cwd=root, check=False)
    today = _dt.date.today().isoformat()

    data = _load(root)
    records = data.setdefault("vouches", [])
    written = 0
    for rel in relpaths:
        text = (root / rel).read_text()
        paras = [p.astext() for p in parse(text).findall(nodes.paragraph)]
        if paragraph is not None:
            if not 1 <= paragraph <= len(paras):
                raise IndexError(
                    f"{rel} has {len(paras)} paragraphs; {paragraph} is out of range"
                )
            paras = [paras[paragraph - 1]]
        for ptext in paras:
            h = para_hash(ptext)
            records[:] = [
                r
                for r in records
                if not (r.get("file") == rel and r.get("hash") == h and r.get("voucher") == name)
            ]
            records.append(
                {
                    "file": rel,
                    "hash": h,
                    "excerpt": ptext[:80],
                    "voucher": name,
                    "email": email,
                    "note": note or "",
                    "date": today,
                    "commit": head,
                }
            )
            written += 1
    _save(root, data)
    if commit and written:
        git("add", "meta/vouches.yaml", cwd=root)
        files = ", ".join(relpaths)
        git("commit", "-m", f"vouch: {name} vouches for {files}", cwd=root)
    return written
