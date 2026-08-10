"""Shared MyST parsing helpers.

Design decisions carried over from the original plan:
- myst-parser (Python) via its docutils integration — never the JS mystmd CLI,
  so parsing and rendering need no network access.
- Sections are *flattened* into a linear list of block nodes before diffing.
- Paragraphs are identified by a content hash of their normalized plain text;
  blame and vouch records key off the same hash so they line up with the
  built HTML (``data-phash`` attributes).
"""

from __future__ import annotations

import hashlib
import re

from docutils import nodes
from docutils.core import publish_doctree
from myst_parser.parsers.docutils_ import Parser as MystParser

MATHJAX_URL = "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"

MYST_OVERRIDES = {
    "myst_enable_extensions": ["dollarmath", "amsmath", "deflist", "colon_fence"],
    # keep parser quiet: diffs/builds must not die on lint-level warnings
    "report_level": 5,
    "halt_level": 5,
}


def parse(text: str) -> nodes.document:
    return publish_doctree(
        text, parser=MystParser(), settings_overrides=dict(MYST_OVERRIDES)
    )


_SKIP_NODES = (
    nodes.comment,
    nodes.system_message,
    nodes.docinfo,
    nodes.meta,
    nodes.field_list,
    nodes.transition,
)


def flatten_blocks(doc: nodes.document) -> list[nodes.Element]:
    """Linearize a doctree into block-level nodes, descending into sections.

    Frontmatter-ish nodes (docinfo, meta, field lists) are dropped, which is
    what makes the AST-level equality check skip frontmatter-only changes.
    """
    blocks: list[nodes.Element] = []

    def walk(parent: nodes.Element) -> None:
        for child in parent.children:
            if isinstance(child, _SKIP_NODES):
                continue
            if isinstance(child, nodes.section):
                walk(child)
            else:
                blocks.append(child)

    walk(doc)
    return blocks


def normalize(text: str) -> str:
    return " ".join(text.split())


def para_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode()).hexdigest()[:16]


def block_signature(node: nodes.Element) -> str:
    return f"{node.tagname}\x00{normalize(node.astext())}"


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def sentences(text: str) -> list[str]:
    return [s for s in _SENT_SPLIT.split(normalize(text)) if s]


def paragraphs_with_lines(doc: nodes.document) -> list[tuple[int | None, str]]:
    """(source line, plain text) for every paragraph, in document order."""
    out = []
    for para in doc.findall(nodes.paragraph):
        line = para.line
        if line is None:
            # myst sometimes leaves .line unset on the paragraph itself but
            # sets it on the first child
            for child in para.children:
                if getattr(child, "line", None) is not None:
                    line = child.line
                    break
        out.append((line, para.astext()))
    return out
