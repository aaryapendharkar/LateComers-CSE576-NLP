"""Config loading. OWNER: Person 1.

``configs/default.yaml`` is shared and committed. Each person edits only their
own section of it. Machine-specific overrides (GPU id, local paths, smaller
models for a laptop) go in ``configs/local.yaml``, which is gitignored, so
nobody's local settings ever land in someone else's checkout.

Precedence: default.yaml < local.yaml < file in $CSE576_CONFIG < explicit overrides.
"""

from __future__ import annotations

import copy
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "configs"


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(overrides: dict | None = None, path: str | os.PathLike | None = None) -> dict[str, Any]:
    cfg = _read_yaml(CONFIG_DIR / "default.yaml")
    cfg = deep_merge(cfg, _read_yaml(CONFIG_DIR / "local.yaml"))
    extra_path = path or os.environ.get("CSE576_CONFIG")
    if extra_path:
        cfg = deep_merge(cfg, _read_yaml(Path(extra_path)))
    if overrides:
        cfg = deep_merge(cfg, overrides)
    return cfg


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    """Cached config for code that just needs the defaults."""
    return load_config()


def resolve(path: str | os.PathLike) -> Path:
    """Resolve a repo-relative path (as stored in configs and JSONL files)."""
    p = Path(path)
    return p if p.is_absolute() else REPO_ROOT / p


def rel(path: str | os.PathLike) -> str:
    """Make a path repo-relative for storing in JSONL (so records work on every machine)."""
    p = Path(path).resolve()
    try:
        return p.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return p.as_posix()
