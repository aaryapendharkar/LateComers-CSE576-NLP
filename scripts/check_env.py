#!/usr/bin/env python
"""Everyone runs this after cloning (Wed kickoff). OWNER: Person 1.

    python scripts/check_env.py
"""
import _bootstrap  # noqa: F401
import importlib
import platform

from src.common.config import load_config, resolve

PKGS = ["numpy", "yaml", "scipy", "pandas", "statsmodels", "datasets", "torch", "transformers",
        "FlagEmbedding", "colpali_engine", "docling", "pdfplumber", "reportlab", "matplotlib", "PIL"]


def main():
    print(f"python {platform.python_version()} on {platform.system()}")
    for p in PKGS:
        try:
            m = importlib.import_module(p)
            print(f"  [ok]      {p} {getattr(m, '__version__', '')}")
        except Exception as e:  # noqa: BLE001
            print(f"  [missing] {p} ({type(e).__name__})")
    try:
        import torch
        print(f"cuda available: {torch.cuda.is_available()}",
              f"({torch.cuda.get_device_name(0)})" if torch.cuda.is_available() else "")
    except ImportError:
        pass
    cfg = load_config()
    print(f"backend={cfg['pipelines']['backend']}  generator={cfg['models']['generator']}")
    for k in ("docs", "examples", "chart_docs", "chart_examples", "qtypes"):
        p = resolve(cfg["paths"][k])
        print(f"  {k:15s} {'exists' if p.exists() else 'not yet'}  {cfg['paths'][k]}")


if __name__ == "__main__":
    main()
