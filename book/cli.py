"""The `book` command-line interface."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from . import __version__


def _root() -> Path:
    from .gitutils import repo_root

    return repo_root()


@click.group()
@click.version_option(__version__, prog_name="book")
def main() -> None:
    """Collaborative document engine: write, diff, review, vouch."""


# --- local workflow ---------------------------------------------------------

@main.command()
@click.argument("directory", default=".")
@click.option("--title", default="Untitled Book", help="Book title.")
def init(directory: str, title: str) -> None:
    """Scaffold a new book repository."""
    from .scaffold import init as do_init

    root = do_init(Path(directory), title=title)
    click.echo(f"Initialized book in {root}")


@main.command()
@click.option("-o", "--output", type=click.Path(), default=None,
              help="Output directory (default _build/html).")
def build(output: str | None) -> None:
    """Build the static HTML site."""
    from .build import build as do_build

    out = do_build(_root(), Path(output) if output else None)
    click.echo(f"Built site in {out}")


@main.command()
@click.argument("file")
def blame(file: str) -> None:
    """Show paragraph-level authorship for a chapter."""
    from .blame import print_blame

    print_blame(_root(), file)


@main.command()
@click.argument("ref", default="main")
@click.option("--render", is_flag=True, help="Produce a rendered HTML diff.")
@click.option("-o", "--output", type=click.Path(), default=None,
              help="Output file for --render (default _build/diff.html).")
@click.option("--open", "open_browser", is_flag=True, help="Open the rendered diff.")
def diff(ref: str, render: bool, output: str | None, open_browser: bool) -> None:
    """Diff the working tree against REF (sentence-level, or rendered HTML)."""
    root = _root()
    if render:
        from .diff import render_diff

        out = render_diff(root, ref, None, out_path=output)
        click.echo(f"Rendered diff written to {out}")
        if open_browser:
            import webbrowser

            webbrowser.open(out.resolve().as_uri())
    else:
        from .diff import terminal_diff

        if not terminal_diff(root, ref, None):
            click.echo("No content changes.")


@main.command()
@click.argument("files", nargs=-1, required=True)
@click.option("--paragraph", "-p", type=int, default=None,
              help="Vouch for a single paragraph (1-based) instead of the whole file.")
@click.option("--note", default=None, help="Optional note stored with the vouch.")
def vouch(files: tuple[str, ...], paragraph: int | None, note: str | None) -> None:
    """Vouch for the paragraphs of one or more chapter files."""
    from .vouch import vouch_files

    n = vouch_files(_root(), list(files), note=note, paragraph=paragraph)
    click.echo(f"Recorded {n} vouch(es) and committed meta/vouches.yaml.")


@main.group()
def change() -> None:
    """Manage local change branches (<username>/<description>)."""


@change.command("new")
@click.argument("description")
def change_new_cmd(description: str) -> None:
    """Start a new change branch."""
    from .changes import change_new

    branch = change_new(_root(), description)
    click.echo(f"Switched to new change branch '{branch}'.")


@change.command("list")
def change_list_cmd() -> None:
    """List local change branches."""
    from .changes import change_list_local

    for b in change_list_local(_root()):
        marker = "*" if b["current"] else " "
        click.echo(f"{marker} {b['name']}  ({b['date']})")


@change.command("switch")
@click.argument("name")
def change_switch_cmd(name: str) -> None:
    """Switch to a change branch."""
    from .changes import change_switch

    click.echo(f"Switched to '{change_switch(_root(), name)}'.")


@main.command()
@click.option("-m", "--message", default=None, help="Commit message.")
def save(message: str | None) -> None:
    """Stage and commit all changes (auto-message if -m omitted)."""
    from .changes import save as do_save

    sha = do_save(_root(), message)
    click.echo(f"Saved as {sha}." if sha else "Nothing to save.")


@main.command()
@click.option("-n", "--limit", default=20, help="Number of commits to show.")
def log(limit: int) -> None:
    """Show recent history."""
    from .changes import log as do_log

    click.echo(do_log(_root(), limit))


# --- remote workflow ----------------------------------------------------------

@main.command()
@click.argument("url")
@click.argument("directory", required=False)
@click.option("--user", default=None, help="Your Forgejo username.")
def clone(url: str, directory: str | None, user: str | None) -> None:
    """Clone a book repository and configure your identity."""
    from .remote import clone as do_clone

    target = do_clone(url, directory, user)
    click.echo(f"Cloned into {target}")


@main.command()
@click.option("--title", default=None, help="Title for the change (PR).")
def submit(title: str | None) -> None:
    """Push your change branch and open (or update) its pull request."""
    from .remote import submit as do_submit

    do_submit(_root(), title)


@main.command()
@click.option("--local", "local_", is_flag=True, help="List local change branches instead.")
@click.option("--state", default="open", type=click.Choice(["open", "closed", "all"]))
def changes(local_: bool, state: str) -> None:
    """List open changes (pull requests) on the forge."""
    if local_:
        from .changes import change_list_local

        for b in change_list_local(_root()):
            marker = "*" if b["current"] else " "
            click.echo(f"{marker} {b['name']}  ({b['date']})")
        return
    from .remote import list_changes, print_changes

    print_changes(list_changes(_root(), state))


@main.command()
@click.argument("number", type=int)
@click.option("--no-open", is_flag=True, help="Don't open the diff in a browser.")
def review(number: int, no_open: bool) -> None:
    """Fetch a change, check it out, and open its rendered diff."""
    from .remote import review as do_review

    do_review(_root(), number, open_browser=not no_open)


@main.command("push-review")
@click.argument("number", type=int)
def push_review_cmd(number: int) -> None:
    """Push your local edits back to a change you are reviewing."""
    from .remote import push_review

    push_review(_root(), number)


@main.command("request-changes")
@click.argument("number", type=int)
@click.option("-m", "--message", required=True, help="What needs to change.")
def request_changes_cmd(number: int, message: str) -> None:
    """Ask the author to revise a change."""
    from .remote import request_changes

    request_changes(_root(), number, message)


@main.command()
@click.argument("number", type=int)
@click.option("--vouch", is_flag=True, help="Vouch for the merged paragraphs.")
@click.option("--note", default=None, help="Note stored with the vouch.")
def approve(number: int, vouch: bool, note: str | None) -> None:
    """Merge a change (merge commit), pull main, optionally vouch."""
    from .remote import approve as do_approve

    do_approve(_root(), number, vouch=vouch, note=note)


if __name__ == "__main__":
    sys.exit(main())
