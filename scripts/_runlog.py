"""Resumable run-log writing shared by the run_* scripts. OWNER: Person 1."""
from pathlib import Path

from src.common.config import resolve
from src.common.io import append_jsonl, read_jsonl


def done_keys(path: Path, key=lambda r: (r["qid"], r.get("attack_id"))) -> set:
    return {key(r) for r in read_jsonl(path)} if path.exists() else set()


def run_path(cfg: dict, pipeline: str, run_name: str) -> Path:
    p = resolve(cfg["paths"]["runs_dir"]) / f"{pipeline}_{run_name}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def log(path: Path, rec: dict) -> None:
    append_jsonl(path, rec)

try:
    from tqdm import tqdm
except ImportError:  # progress bars are optional
    def tqdm(it, **_):
        return it
