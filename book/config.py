"""Configuration handling.

Precedence (highest wins):
  1. environment (``BOOK_TOKEN``)
  2. repo-local ``.book/config.toml``   (never committed; .gitignore'd)
  3. user-level ``~/.config/book/config.toml``

Remote coordinates (Forgejo base URL, owner, repo) are normally *derived*
from the ``origin`` remote URL, so they never need duplicating in config;
config can override them under ``[forgejo]``.
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

from .gitutils import git

USER_CONFIG = Path(os.environ.get("BOOK_CONFIG_HOME", Path.home() / ".config" / "book")) / "config.toml"


def _read_toml(path: Path) -> dict:
    try:
        return tomllib.loads(Path(path).read_text())
    except (FileNotFoundError, NotADirectoryError):
        return {}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(repo: Path | None = None) -> dict:
    cfg = _read_toml(USER_CONFIG)
    if repo is not None:
        cfg = _merge(cfg, _read_toml(Path(repo) / ".book" / "config.toml"))
    if os.environ.get("BOOK_TOKEN"):
        cfg.setdefault("forgejo", {})["token"] = os.environ["BOOK_TOKEN"]
    return cfg


def _toml_dump(data: dict) -> str:
    """Minimal TOML writer for our flat [section] -> {str: str} config."""
    lines: list[str] = []
    scalars = {k: v for k, v in data.items() if not isinstance(v, dict)}
    for k, v in scalars.items():
        lines.append(f'{k} = "{v}"')
    for section, values in data.items():
        if not isinstance(values, dict):
            continue
        lines.append(f"[{section}]")
        for k, v in values.items():
            lines.append(f'{k} = "{v}"')
        lines.append("")
    return "\n".join(lines) + "\n"


def write_local_config(repo: Path, data: dict) -> Path:
    path = Path(repo) / ".book" / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_toml(path)
    path.write_text(_toml_dump(_merge(existing, data)))
    return path


def parse_remote_url(url: str) -> tuple[str, str, str]:
    """Split a clone URL into (forgejo base url, owner, repo)."""
    if url.startswith("file://"):
        # local test remotes: no API base derivable; config must supply it
        parts = [p for p in url[len("file://"):].split("/") if p]
        owner = parts[-2] if len(parts) >= 2 else "local"
        return "", owner, parts[-1].removesuffix(".git")
    if url.startswith("git@"):
        host, path = url[4:].split(":", 1)
        base = f"https://{host}"
    else:
        m = re.match(r"(https?://[^/]+)(/.*)", url)
        if not m:
            raise ValueError(f"cannot parse remote URL: {url}")
        base, path = m.group(1), m.group(2)
    parts = [p for p in path.strip("/").split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"cannot parse owner/repo from remote URL: {url}")
    owner, repo = parts[-2], parts[-1].removesuffix(".git")
    prefix = "/".join(parts[:-2])
    if prefix:
        base = f"{base}/{prefix}"
    return base, owner, repo


def remote_coords(repo: Path) -> tuple[str, str, str]:
    """Forgejo (base_url, owner, repo) for this checkout.

    Config overrides win; otherwise derived from the origin remote.
    """
    cfg = load_config(repo).get("forgejo", {})
    origin = git("remote", "get-url", "origin", cwd=repo, check=False)
    base = owner = name = None
    if origin:
        try:
            base, owner, name = parse_remote_url(origin)
        except ValueError:
            pass
    base = cfg.get("url", base)
    owner = cfg.get("owner", owner)
    name = cfg.get("repo", name)
    if not (base and owner and name):
        raise RuntimeError(
            "cannot determine Forgejo remote; set [forgejo] url/owner/repo in "
            f"{USER_CONFIG} or .book/config.toml, or add an 'origin' remote"
        )
    return base, owner, name


def username(repo: Path | None = None) -> str | None:
    return load_config(repo).get("user", {}).get("name")


def token(repo: Path | None = None) -> str | None:
    return load_config(repo).get("forgejo", {}).get("token")
