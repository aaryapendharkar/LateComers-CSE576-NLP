# How we work together without stepping on each other

Five people, one repo, four days. These rules keep everyone's work separate.

## 1. Who owns what

You edit **only the files you own**. If you need a change in someone else's file, message them or open an issue. Don't edit it yourself.

| # | Person | Branch | Owns (code) | Owns (output files) | Tests |
|---|--------|--------|-------------|---------------------|-------|
| 1 | Aarya | `p1-pipelines` | `src/common/*`, `src/data/*`, `src/pipelines/*`, `scripts/{check_env,prepare_finqa,build_indexes,run_baselines,run_attacks,summarize,_bootstrap,_runlog}.py`, `configs/` (shared sections), README, CI | `data/docs.jsonl`, `data/examples.jsonl`, `results/runs/`, `results/r2_correct.json`, `results/baselines/`, `results/funnel*.csv` | `tests/common/` |
| 2 | Janhavi | `p2-table-attacks` | `src/attacks/tables/*`, `scripts/make_g1_attacks.py` | `data/attacks/g1.jsonl`, `data/manifests/pages_g1.jsonl`, `results/gap1/edit_stats*` | `tests/test_p2_*.py` |
| 3 | Vatsal | `p3-table-defense` | `src/defenses/reconcile.py`, `src/analysis/{qtypes,stealth,funnel}.py`, `scripts/{label_qtypes,eval_reconcile,stealth_study}.py` | `data/labels/qtypes.jsonl`, `results/gap1/d1_*`, `results/gap1/stealth_*` | `tests/test_p3_*.py` |
| 4 | Aaron | `p4-renderer` | `src/render/*`, `src/attacks/representation/*`, `scripts/{render_clean_pages,prepare_chartqa,make_g2_attacks}.py` | `data/manifests/pages_clean*.jsonl`, `data/manifests/pages_g2.jsonl`, `data/attacks/g2.jsonl`, `data/chart_docs.jsonl`, `data/chart_examples.jsonl` | `tests/test_p4_*.py` |
| 5 | Disha | `p5-gap2-defense` | `src/defenses/img_text_check.py`, `src/analysis/which_wins.py`, `scripts/{eval_img_text_check,which_wins}.py` | `results/gap2/checker_*`, `results/gap2/which_wins*` | `tests/test_p5_*.py` |

New helper files are fine; put them in your own folder (e.g. `src/render/fonts.py`).

## 2. Shared contract files (change only by agreement)

These define how our parts plug together. To change one, open a PR **and** post in the group chat first:

- `src/common/schemas.py`: the A6 JSONL formats (field names, attack types, id helpers)
- `src/common/edits.py`: the format of `attack["edit"]`
- Function signatures in A7: `render_table_page(...)`, `run_query(...)`, `numbers_match(...)`

Adding an **optional** field with a default is fine (say so in your PR). Renaming or removing a field is not, unless the group agrees.

## 3. One writer per output file

Two people never write the same file. That's why there are several manifest/attack files instead of one `pages.jsonl` / `attacks.jsonl`. The loaders in `src/common/io.py` merge them:

- `load_pages()` reads every `data/manifests/pages_*.jsonl`
- `load_attacks()` reads every `data/attacks/*.jsonl`
- `load_examples()` overlays Person 3's `data/labels/qtypes.jsonl` onto `examples.jsonl`

Small JSONL/CSV files in `data/` and `results/` **are committed** so teammates can pull them. Heavy files (`data/raw/`, `data/pages/`, `data/parsed/`, `data/indexes/`) are gitignored; share rendered pages through the team drive folder.

## 4. Git workflow

```bash
git checkout p2-table-attacks          # your branch (once)
git pull origin main                   # every morning, and after any "merged!" message
git merge main                         # bring main into your branch
# ... work, commit often ...
git add src/attacks/tables/ tests/test_p2_table_attacks.py
git commit -m "[P2] program executor reproduces 96% of gold answers"
git push origin p2-table-attacks
```

Then open a Pull Request `your-branch → main` on GitHub. Aarya reviews and merges. CI (`pytest`) must be green.

- **Commit often, with a `[P#]` prefix.** The report lists what each member completed; commit history is the evidence.
- Use `git add <your paths>`, not `git add .`, so you never commit someone else's file by accident.
- Don't commit `configs/local.yaml`, data dumps, model weights, API keys or tokens.
- Keep PRs small (one feature each). Several merges a day beat one huge merge on Saturday.

## 5. Config

`configs/default.yaml` has a section per owner; edit only yours. Settings that only apply to your machine (GPU, a smaller model, scratch paths) go in `configs/local.yaml` (copy `configs/local.example.yaml`). That file is gitignored, so it never reaches anyone else.

## 6. Build against mocks first

Nobody waits for anybody. Hand-made fixture data (3 FinQA docs, 1 chart, sample Gap 1/Gap 2 attacks) lives in `tests/fixtures/`. Run any script against it with a fake GPU-free backend:

```bash
export CSE576_CONFIG=tests/fixtures/config.yaml    # Windows PowerShell: $env:CSE576_CONFIG="tests/fixtures/config.yaml"
python scripts/run_baselines.py --pipelines P1
python scripts/run_attacks.py --pipeline P1 --gap G1
```

Your acceptance tests (`tests/test_p#_*.py`) are already written from the "Done when" list in your brief. They show as **skipped** while your function still raises `NotImplementedError`, and switch on automatically when you implement it:

```bash
pytest tests/test_p2_table_attacks.py -rs
```

If you think a test is wrong, tell Aarya. Don't delete it.

## 7. Report contributions (Sat 8 pm)

Copy `report/contributions/TEMPLATE.md` to `report/contributions/p<#>_<name>.md`, fill it in, and put figures in `report/figures/p<#>_*.png`. Separate files mean no merge conflicts.
