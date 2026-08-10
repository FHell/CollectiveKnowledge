"""`book build` — MyST chapters -> static HTML site in _build/html/.

The site is fully static and uses only *relative* asset paths, so it works
served from any URL prefix (Phase 0 requirement). Every paragraph carries a
``data-phash`` attribute; overlay.js joins that against blame.json and
vouches.json at click time.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml
from docutils.core import publish_parts
from docutils.writers.html5_polyglot import HTMLTranslator, Writer
from myst_parser.parsers.docutils_ import Parser as MystParser

from .blame import file_blame
from .mystdoc import MATHJAX_URL, MYST_OVERRIDES, para_hash

ASSETS = Path(__file__).parent / "assets"

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="style.css">
<script defer src="{mathjax}"></script>
</head>
<body>
<nav class="bk-nav">{nav}</nav>
<main class="bk-main" data-source="{source}">
{body}
</main>
<script src="forge-client.js"></script>
<script src="overlay.js"></script>
<script src="web-actions.js" data-base="./"></script>
</body>
</html>
"""


class BookTranslator(HTMLTranslator):
    """HTML translator that stamps each paragraph with its content hash."""

    def visit_paragraph(self, node):
        self.body.append(
            self.starttag(node, "p", "", **{"data-phash": para_hash(node.astext())})
        )

    def depart_paragraph(self, node):
        self.body.append("</p>\n")


def render_page_body(text: str) -> tuple[str, str]:
    """(body html, title) for one chapter source."""
    writer = Writer()
    writer.translator_class = BookTranslator
    parts = publish_parts(
        text,
        parser=MystParser(),
        writer=writer,
        settings_overrides={
            **MYST_OVERRIDES,
            "math_output": f"mathjax {MATHJAX_URL}",
            "embed_stylesheet": False,
        },
    )
    return parts["body"], parts["title"] or ""


def chapter_files(root: Path) -> list[str]:
    """Chapter file list from _toc.yml, falling back to a glob."""
    toc = root / "_toc.yml"
    files: list[str] = []
    if toc.exists():
        data = yaml.safe_load(toc.read_text()) or {}
        for entry in data.get("chapters", []):
            f = entry.get("file") if isinstance(entry, dict) else entry
            if f:
                files.append(str(f))
    for p in sorted((root / "chapters").glob("*.md")):
        rel = str(p.relative_to(root))
        if rel not in files:
            files.append(rel)
    return [f for f in files if (root / f).exists()]


def _load_vouches(root: Path) -> dict[str, list[dict]]:
    path = root / "meta" / "vouches.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    by_hash: dict[str, list[dict]] = {}
    for entry in data.get("vouches", []):
        by_hash.setdefault(entry.get("hash", ""), []).append(
            {
                "voucher": entry.get("voucher", ""),
                "note": entry.get("note", ""),
                "date": entry.get("date", ""),
                "commit": entry.get("commit", ""),
            }
        )
    return by_hash


def _title_of(root: Path) -> str:
    import tomllib

    try:
        return tomllib.loads((root / "book.toml").read_text())["book"]["title"]
    except Exception:
        return "Book"


def build(root: Path, out_dir: Path | None = None) -> Path:
    root = Path(root)
    out = Path(out_dir) if out_dir else root / "_build" / "html"
    out.mkdir(parents=True, exist_ok=True)

    book_title = _title_of(root)
    files = chapter_files(root)
    pages = []  # (relpath, outname, title)

    for rel in files:
        text = (root / rel).read_text()
        body, title = render_page_body(text)
        outname = Path(rel).stem + ".html"
        pages.append((rel, outname, title or Path(rel).stem))
        (out / outname).write_text(
            PAGE_TEMPLATE.format(title=title or book_title, nav="", body=body,
                                 mathjax=MATHJAX_URL, source=rel)
        )

    # nav bar (index + all chapters) written into every page in a 2nd pass
    nav_html = '<a href="index.html">☰ ' + book_title + "</a>" + "".join(
        f' · <a href="{o}">{t}</a>' for _, o, t in pages
    )
    for _, outname, _ in pages:
        p = out / outname
        p.write_text(p.read_text().replace('<nav class="bk-nav"></nav>',
                                           f'<nav class="bk-nav">{nav_html}</nav>'))

    toc_items = "\n".join(
        f'<li><a href="{o}">{t}</a></li>' for _, o, t in pages
    )
    (out / "index.html").write_text(
        PAGE_TEMPLATE.format(
            title=book_title,
            nav=nav_html,
            body=f"<h1>{book_title}</h1>\n<ul class='bk-toc'>\n{toc_items}\n</ul>",
            mathjax=MATHJAX_URL,
            source="",
        )
    )

    # blame.json — paragraph-level authorship, keyed by content hash
    blame_files: dict[str, list[dict]] = {}
    by_hash: dict[str, dict] = {}
    for rel in files:
        try:
            entries = file_blame(root, rel)
        except Exception:
            entries = []
        blame_files[rel] = entries
        for e in entries:
            by_hash[e["hash"]] = {**e, "file": rel}
    (out / "blame.json").write_text(
        json.dumps({"files": blame_files, "byHash": by_hash}, indent=1)
    )

    # vouches.json — hash -> list of vouch records
    (out / "vouches.json").write_text(json.dumps(_load_vouches(root), indent=1))

    for asset in ("style.css", "overlay.js", "forge-client.js", "web-actions.js"):
        shutil.copy(ASSETS / asset, out / asset)

    # forge.json — lets the in-browser client (web-actions.js) talk to the
    # forge API. Best-effort: without an origin remote the site is
    # read-only and the interactive layer disables itself.
    forge_cfg = forge_site_config(root)
    if forge_cfg:
        (out / "forge.json").write_text(json.dumps(forge_cfg, indent=1))
    return out


def forge_site_config(root: Path) -> dict | None:
    from .config import remote_coords

    try:
        base, owner, name = remote_coords(root)
    except Exception:
        return None
    if not base:
        return None
    from urllib.parse import urlparse

    host = urlparse(base).netloc
    if host == "github.com":
        provider, api = "github", "https://api.github.com"
    else:
        provider, api = "gitea", f"{base.rstrip('/')}/api/v1"
    return {
        "provider": provider,
        "api": api,
        "owner": owner,
        "repo": name,
        "branch": "main",
        "html": f"{base.rstrip('/')}/{owner}/{name}",
    }
