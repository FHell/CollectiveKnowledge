"""`book diff` — sentence-level terminal diff and AST-level rendered HTML diff.

Pipeline for the rendered diff (kept from the original design):
myst-parser -> flattened block nodes -> SequenceMatcher over block
signatures -> inline-level diff of paragraph pairs -> custom
``diff_insert``/``diff_delete`` docutils nodes -> ``<ins>``/``<del>`` HTML
with typeset math.

``render_diff()`` is the programmatic entry point CI uses; the CLI is a thin
wrapper around it.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

from docutils import nodes as dn
from docutils.core import publish_from_doctree
from docutils.writers.html5_polyglot import HTMLTranslator, Writer

from .gitutils import file_at_ref, ls_tree_md
from .mystdoc import (
    MATHJAX_URL,
    block_signature,
    flatten_blocks,
    parse,
    sentences,
)


# --- custom nodes -----------------------------------------------------------

class diff_insert(dn.Inline, dn.TextElement):
    pass


class diff_delete(dn.Inline, dn.TextElement):
    pass


class diff_block(dn.General, dn.Element):
    pass


class DiffTranslator(HTMLTranslator):
    def visit_diff_insert(self, node):
        self.body.append('<ins class="bk-diff">')

    def depart_diff_insert(self, node):
        self.body.append("</ins>")

    def visit_diff_delete(self, node):
        self.body.append('<del class="bk-diff">')

    def depart_diff_delete(self, node):
        self.body.append("</del>")

    def visit_diff_block(self, node):
        self.body.append(f'<div class="bk-diff-block bk-diff-{node["kind"]}">\n')

    def depart_diff_block(self, node):
        self.body.append("</div>\n")


# --- helpers ----------------------------------------------------------------

def _copy(node: dn.Element) -> dn.Element:
    """Deep copy a node, dropping ids/names to avoid duplicate anchors."""
    new = node.deepcopy()
    for n in new.findall():
        if isinstance(n, dn.Element):
            n["ids"] = []
            n["names"] = []
    return new


def _as_diffable(node: dn.Element) -> dn.Element:
    """Titles can't live outside sections in the HTML writer; re-home them."""
    if isinstance(node, dn.title):
        para = dn.paragraph(classes=["bk-heading"])
        for child in _copy(node).children:
            para += child
        return para
    return _copy(node)


def _wrap(block_nodes: list[dn.Element], kind: str) -> diff_block:
    w = diff_block(kind=kind)
    for b in block_nodes:
        w += _as_diffable(b)
    return w


# --- inline (word-level) diff of a paragraph pair ---------------------------

_WORD = re.compile(r"\S+\s*|\s+")


def _tokenize_inline(para: dn.Element) -> list[tuple[str, object]]:
    toks: list[tuple[str, object]] = []
    for child in para.children:
        if isinstance(child, dn.Text):
            for m in _WORD.finditer(child.astext()):
                toks.append(("w", m.group()))
        else:
            toks.append(("n", child))
    return toks


def _tok_key(tok: tuple[str, object]) -> str:
    kind, v = tok
    if kind == "w":
        return str(v).strip()
    return f"{v.tagname}\x00{' '.join(v.astext().split())}"


def _append_tokens(parent: dn.Element, toks: list[tuple[str, object]]) -> None:
    for kind, v in toks:
        if kind == "w":
            parent += dn.Text(str(v))
        else:
            parent += _as_diffable(v)


_TEX_TOKEN = re.compile(r"\\[A-Za-z]+|\s+|.")


def _math_intradiff(old: str, new: str) -> tuple[dn.math, dn.math] | None:
    """Character/command-level diff inside a formula.

    Changed TeX tokens are wrapped in MathJax's ``\\class{}`` so the changed
    symbol itself is highlighted in the typeset output. Falls back to None
    (formula treated atomically) when the formulas are too different.
    """
    a = _TEX_TOKEN.findall(old)
    b = _TEX_TOKEN.findall(new)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    if sm.ratio() < 0.5:
        return None
    old_out: list[str] = []
    new_out: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            old_out += a[i1:i2]
            new_out += b[j1:j2]
        else:
            if i2 > i1:
                old_out.append(r"\class{bk-mdel}{" + "".join(a[i1:i2]) + "}")
            if j2 > j1:
                new_out.append(r"\class{bk-mins}{" + "".join(b[j1:j2]) + "}")
    return (
        dn.math(text="".join(old_out)),
        dn.math(text="".join(new_out)),
    )


def _inline_diff_paragraph(a: dn.Element, b: dn.Element) -> dn.paragraph:
    ta, tb = _tokenize_inline(a), _tokenize_inline(b)
    ka = [_tok_key(t) for t in ta]
    kb = [_tok_key(t) for t in tb]
    para = dn.paragraph(classes=["bk-diff-para"])
    sm = difflib.SequenceMatcher(a=ka, b=kb, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            _append_tokens(para, tb[j1:j2])
            continue
        # single math node replaced by single math node: try symbol-level diff
        if (
            tag == "replace"
            and i2 - i1 == 1
            and j2 - j1 == 1
            and ta[i1][0] == "n"
            and tb[j1][0] == "n"
            and isinstance(ta[i1][1], dn.math)
            and isinstance(tb[j1][1], dn.math)
        ):
            pair = _math_intradiff(ta[i1][1].astext(), tb[j1][1].astext())
            if pair is not None:
                old_m, new_m = pair
                d = diff_delete()
                d += old_m
                para += d
                para += dn.Text(" ")
                ins = diff_insert()
                ins += new_m
                para += ins
                continue
        if i2 > i1:
            d = diff_delete()
            _append_tokens(d, ta[i1:i2])
            para += d
        if j2 > j1:
            ins = diff_insert()
            _append_tokens(ins, tb[j1:j2])
            para += ins
    return para


# --- block-level diff -------------------------------------------------------

def diff_block_nodes(
    base_blocks: list[dn.Element], head_blocks: list[dn.Element]
) -> list[dn.Element]:
    out: list[dn.Element] = []
    sigs_a = [block_signature(b) for b in base_blocks]
    sigs_b = [block_signature(b) for b in head_blocks]
    sm = difflib.SequenceMatcher(a=sigs_a, b=sigs_b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out += [_as_diffable(b) for b in head_blocks[j1:j2]]
        elif tag == "delete":
            out.append(_wrap(base_blocks[i1:i2], "delete"))
        elif tag == "insert":
            out.append(_wrap(head_blocks[j1:j2], "insert"))
        else:  # replace — pair blocks up in order
            a_list, b_list = base_blocks[i1:i2], head_blocks[j1:j2]
            n = min(len(a_list), len(b_list))
            for k in range(n):
                a, b = a_list[k], b_list[k]
                if isinstance(a, dn.paragraph) and isinstance(b, dn.paragraph):
                    out.append(_inline_diff_paragraph(a, b))
                else:
                    out.append(_wrap([a], "delete"))
                    out.append(_wrap([b], "insert"))
            for a in a_list[n:]:
                out.append(_wrap([a], "delete"))
            for b in b_list[n:]:
                out.append(_wrap([b], "insert"))
    return out


# --- file collection --------------------------------------------------------

def _chapter_union(root: Path, base_ref: str, head_ref: str | None) -> list[str]:
    files = ls_tree_md(root, base_ref)
    if head_ref:
        head_files = ls_tree_md(root, head_ref)
    else:
        head_files = [
            str(p.relative_to(root)) for p in sorted((root / "chapters").glob("*.md"))
        ]
    for f in head_files:
        if f not in files:
            files.append(f)
    return sorted(files)


def _text_at(root: Path, ref: str | None, relpath: str) -> str:
    if ref is None:  # working tree
        p = root / relpath
        return p.read_text() if p.exists() else ""
    return file_at_ref(root, ref, relpath) or ""


def changed_files(root: Path, base_ref: str, head_ref: str | None = None) -> list[str]:
    """Chapters whose flattened AST differs between the two refs."""
    changed = []
    for rel in _chapter_union(root, base_ref, head_ref):
        base_text = _text_at(root, base_ref, rel)
        head_text = _text_at(root, head_ref, rel)
        if base_text == head_text:
            continue
        base_sigs = [block_signature(b) for b in flatten_blocks(parse(base_text))]
        head_sigs = [block_signature(b) for b in flatten_blocks(parse(head_text))]
        if base_sigs != head_sigs:
            changed.append(rel)
    return changed


# --- rendered diff (the CI-callable entry point) -----------------------------

DIFF_CSS = """
body { font-family: Georgia, 'Times New Roman', serif; line-height: 1.6;
       max-width: 46rem; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
.bk-file { font-family: ui-monospace, monospace; font-size: .9rem;
           color: #555; border-bottom: 2px solid #ddd; margin-top: 2.5rem;
           padding-bottom: .3rem; }
ins.bk-diff { background: #d8f5d3; color: #14520f; text-decoration: none; }
del.bk-diff { background: #fbdddd; color: #8f1d1d; }
.bk-diff-block { border-left: 4px solid transparent; padding: .1rem .6rem;
                 margin: .4rem 0; }
.bk-diff-insert { border-left-color: #3fa34d; background: #f0fbee; }
.bk-diff-delete { border-left-color: #cc4444; background: #fdf3f3;
                  text-decoration: line-through; color: #8f1d1d; }
.bk-heading { font-weight: bold; font-size: 1.3rem; }
.bk-mins { color: #147a24 !important; background: #d8f5d3; }
.bk-mdel { color: #b31d1d !important; background: #fbdddd; }
.bk-empty { color: #666; font-style: italic; }
h1.bk-title { font-size: 1.4rem; border-bottom: 3px double #999;
              padding-bottom: .4rem; }
"""


def render_diff(
    repo_path: Path | str,
    base_ref: str,
    head_ref: str | None = None,
    out_path: Path | str | None = None,
    title: str | None = None,
) -> Path:
    """Render an HTML diff of the book between two refs.

    ``head_ref=None`` compares against the working tree. Returns the path of
    the written HTML file (single, self-contained page; math typeset by
    MathJax loaded client-side).
    """
    root = Path(repo_path).resolve()
    out = Path(out_path) if out_path else root / "_build" / "diff.html"
    out.parent.mkdir(parents=True, exist_ok=True)

    host = parse("")  # empty document with proper settings/reporter
    head_label = head_ref or "working tree"
    title = title or f"Rendered diff: {base_ref} → {head_label}"
    host += dn.raw("", f"<h1 class='bk-title'>{title}</h1>", format="html")

    any_changes = False
    for rel in _chapter_union(root, base_ref, head_ref):
        base_text = _text_at(root, base_ref, rel)
        head_text = _text_at(root, head_ref, rel)
        if base_text == head_text:
            continue
        base_blocks = flatten_blocks(parse(base_text))
        head_blocks = flatten_blocks(parse(head_text))
        # AST-level equality: skip frontmatter/whitespace-only differences
        if [block_signature(b) for b in base_blocks] == [
            block_signature(b) for b in head_blocks
        ]:
            continue
        any_changes = True
        host += dn.raw("", f"<div class='bk-file'>{rel}</div>", format="html")
        for node in diff_block_nodes(base_blocks, head_blocks):
            host += node

    if not any_changes:
        host += dn.paragraph(
            text="No content changes between these revisions.", classes=["bk-empty"]
        )

    writer = Writer()
    writer.translator_class = DiffTranslator
    html = publish_from_doctree(
        host,
        writer=writer,
        settings_overrides={
            "output_encoding": "unicode",
            "math_output": f"mathjax {MATHJAX_URL}",
            "embed_stylesheet": False,
            "stylesheet_path": "",
            "report_level": 5,
        },
    )
    inject = (
        f"<style>{DIFF_CSS}</style>\n"
        f'<script defer src="{MATHJAX_URL}"></script>\n</head>'
    )
    html = html.replace("</head>", inject, 1)
    Path(out).write_text(html)
    return Path(out)


# --- terminal diff ----------------------------------------------------------

_RED = "\x1b[31m"
_GREEN = "\x1b[32m"
_DIM = "\x1b[2m"
_RESET = "\x1b[0m"


def terminal_diff(root: Path, base_ref: str, head_ref: str | None = None) -> bool:
    """Print a sentence-level diff to stdout. Returns True if changes exist."""
    changed = False
    for rel in _chapter_union(root, base_ref, head_ref):
        base_text = _text_at(root, base_ref, rel)
        head_text = _text_at(root, head_ref, rel)
        if base_text == head_text:
            continue
        base_blocks = flatten_blocks(parse(base_text))
        head_blocks = flatten_blocks(parse(head_text))
        sigs_a = [block_signature(b) for b in base_blocks]
        sigs_b = [block_signature(b) for b in head_blocks]
        if sigs_a == sigs_b:
            continue
        changed = True
        print(f"{_DIM}── {rel} ──{_RESET}")
        sm = difflib.SequenceMatcher(a=sigs_a, b=sigs_b, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            if tag in ("delete", "replace"):
                for b in base_blocks[i1:i2]:
                    _print_block(b, head_blocks[j1:j2] if tag == "replace" else None)
            if tag == "insert":
                for b in head_blocks[j1:j2]:
                    for s in sentences(b.astext()):
                        print(f"{_GREEN}+ {s}{_RESET}")
        print()
    return changed


def _print_block(base_block: dn.Element, head_candidates) -> None:
    base_sents = sentences(base_block.astext())
    if head_candidates:
        # sentence-level diff against the best-matching head block
        best = max(
            head_candidates,
            key=lambda h: difflib.SequenceMatcher(
                a=base_block.astext(), b=h.astext()
            ).ratio(),
            default=None,
        )
        if best is not None:
            head_sents = sentences(best.astext())
            sm = difflib.SequenceMatcher(a=base_sents, b=head_sents, autojunk=False)
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag == "equal":
                    continue
                for s in base_sents[i1:i2]:
                    print(f"{_RED}- {s}{_RESET}")
                for s in head_sents[j1:j2]:
                    print(f"{_GREEN}+ {s}{_RESET}")
            return
    for s in base_sents:
        print(f"{_RED}- {s}{_RESET}")
