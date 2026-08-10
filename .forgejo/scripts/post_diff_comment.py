#!/usr/bin/env python3
"""Post (or update in place) the rendered-diff link comment on a PR.

Runs inside CI. Uses the standard Forgejo Actions environment plus:
  BOOK_TOKEN — API token with issue-write scope (secret CI_TOKEN)
  SITE_URL   — public base URL of the static host (repo variable)
"""

import os
import sys

from book.forge import Forge

MARKER = "<!-- book-rendered-diff -->"


def main() -> int:
    number = int(sys.argv[1])
    base = os.environ["GITHUB_SERVER_URL"].rstrip("/")
    owner, repo = os.environ["GITHUB_REPOSITORY"].split("/", 1)
    site = os.environ.get("SITE_URL", "").rstrip("/")
    if not site:
        print("SITE_URL not set; skipping PR comment", file=sys.stderr)
        return 0
    url = f"{site}/diffs/pr-{number}/"
    forge = Forge(base, owner, repo, token=os.environ["BOOK_TOKEN"])
    forge.upsert_comment(
        number,
        MARKER,
        f"**Rendered diff:** {url}\n\n"
        f"_Regenerated automatically on every push to this change._",
    )
    print(f"diff link comment set: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
