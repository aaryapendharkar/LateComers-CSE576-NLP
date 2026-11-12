#!/usr/bin/env bash
# Person 1 (Aarya): every step of my part, one command each. Run from the repo root.
#
#   bash scripts/p1_steps.sh setup       # Thu morning  - install + download FinQA
#   bash scripts/p1_steps.sh inspect     # Thu morning  - show T2-RAGBench column names
#   bash scripts/p1_steps.sh data        # Thu by noon  - make data/docs.jsonl + data/examples.jsonl
#   bash scripts/p1_steps.sh smoke       # Thu (GPU)    - 5 questions through P1 to test the models
#   bash scripts/p1_steps.sh index       # Fri (GPU)    - after Aaron's pages: parse + embed all pages
#   bash scripts/p1_steps.sh baselines   # Fri (GPU)    - R1/R2/R3 + results/r2_correct.json (by 9 pm)
#   bash scripts/p1_steps.sh charts      # Fri night    - chart baselines (after Aaron's chart data)
#   bash scripts/p1_steps.sh attacks     # Sat (GPU)    - run Gap 1 + Gap 2 attacks
#   bash scripts/p1_steps.sh summary     # Sat          - funnel tables for the report
#
# After each step: git add <the files it lists> && git commit -m "[P1] ..." && git push
set -euo pipefail
PIPES="${PIPES:-P1 P2}"   # add P3 when it works:  PIPES="P1 P2 P3" bash scripts/p1_steps.sh baselines

case "${1:-}" in
  setup)
    pip install -r requirements.txt
    [ -d data/raw/FinQA ] || git clone --depth 1 https://github.com/czyssrs/FinQA data/raw/FinQA
    [ -f configs/local.yaml ] || cp configs/local.example.yaml configs/local.yaml
    python scripts/check_env.py
    ;;
  inspect)
    python scripts/prepare_finqa.py --inspect
    echo ">> Compare the column names above with data.finqa.fields in configs/default.yaml and fix them."
    ;;
  data)
    python scripts/prepare_finqa.py \
      --finqa-json data/raw/FinQA/dataset/test.json data/raw/FinQA/dataset/dev.json \
      --distractor-split dev
    echo ">> Expect n_docs=500, n_examples=200, joined and with_program close to 200."
    echo ">> Commit: data/docs.jsonl data/examples.jsonl  -> then message Janhavi + Aaron."
    ;;
  smoke)
    python scripts/run_baselines.py --pipelines P1 --runs R2 --limit 5
    echo ">> Open results/runs/P1_R2_finqa.jsonl: answers should be numbers, 'cited' should list page ids."
    echo ">> These 5 lines are a test: delete results/runs/P1_R2_finqa.jsonl before the real run."
    ;;
  index)
    python scripts/build_indexes.py --parse docling --limit 5
    echo ">> Check 5 files in data/parsed/docling/ by hand: is the table there with the right numbers?"
    read -r -p "Tables look right? [y = continue with docling / n = use pdfplumber] " ok
    if [ "$ok" = "y" ]; then PARSER=docling; else PARSER=pdfplumber; fi
    python scripts/build_indexes.py --parse "$PARSER"
    python scripts/build_indexes.py --index P1 P2
    echo ">> Now set  pipelines: {p1_text_source: $PARSER}  in configs/local.yaml"
    ;;
  baselines)
    python scripts/run_baselines.py --pipelines $PIPES
    echo ">> Commit: results/r2_correct.json results/baselines/ results/runs/  -> send r2_correct.json to Janhavi + Aaron."
    ;;
  charts)
    python scripts/build_indexes.py --parse "$(python -c 'from src.common.config import get_config as g; print(g()["pipelines"]["p1_text_source"])')"
    python scripts/build_indexes.py --index P1 P2
    python scripts/run_baselines.py --source chartqa --pipelines $PIPES
    ;;
  attacks)
    python scripts/build_indexes.py --parse "$(python -c 'from src.common.config import get_config as g; print(g()["pipelines"]["p1_text_source"])')"
    for P in $PIPES; do
      python scripts/run_attacks.py --pipeline "$P" --gap G1 --run-name G1
      python scripts/run_attacks.py --pipeline "$P" --gap G2 --run-name G2
    done
    echo ">> Commit: results/runs/"
    ;;
  summary)
    python scripts/summarize.py --runs results/runs/*_G1.jsonl --out results/gap1/funnel.csv
    python scripts/summarize.py --runs results/runs/*_G2.jsonl --out results/gap2/funnel.csv
    echo ">> Commit: results/gap1/funnel.csv results/gap2/funnel.csv"
    ;;
  *)
    sed -n '2,15p' "$0"; exit 1 ;;
esac
