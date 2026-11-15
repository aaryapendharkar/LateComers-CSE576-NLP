import _bootstrap
import argparse

from src.common.config import get_config
from src.common.metrics import fmt_rate
from src.defenses.img_text_check import evaluate, reading_accuracy


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-clean", type=int, default=None, help="clean pages per source (default 100)")
    ap.add_argument("--oracle", action="store_true", help="perfect image reader for dry runs, writes *_oracle files")
    ap.add_argument("--out-dir", default="results/gap2")
    ap.add_argument("--overwrite", action="store_true", help="start over instead of resuming")
    ap.add_argument("--limit", type=int, help="check only the first N pages (quick test)")
    ap.add_argument("--read-accuracy", action="store_true", help="also score the VLM reads against the drawn tables")
    ap.add_argument("--cached-only", action="store_true", help="no model: only pages the model has already read")
    args = ap.parse_args()

    cfg = get_config()
    rows = evaluate(cfg, n_clean=args.n_clean, oracle=args.oracle,
                    out_dir=args.out_dir, overwrite=args.overwrite, limit=args.limit,
                    cached_only=args.cached_only)
    for r in rows:
        print(f"{r['kind']:18s} {r['metric']:20s} {fmt_rate(r)}  errors={r['errors']}")
    print(f"wrote {args.out_dir}/checker_table{'_oracle' if args.oracle else ''}.md")
    if args.read_accuracy and not args.oracle:
        for kind, r in reading_accuracy(cfg, args.out_dir).items():
            print(f"VLM read {kind}s exactly: {fmt_rate(r)}")


if __name__ == "__main__":
    main()
