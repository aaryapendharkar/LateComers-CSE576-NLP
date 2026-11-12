#!/usr/bin/env bash
# One-time setup (Person 1). Run from the repo root after unzipping.
#   bash scripts/setup_github.sh <github-user-or-org>
# Needs git, and the GitHub CLI (`gh auth login`) for the create step.
# Without gh: create an EMPTY private repo named cse576-structured-poisoning on
# github.com, then run this script with SKIP_CREATE=1.
set -euo pipefail
OWNER="${1:?usage: setup_github.sh <github-user-or-org>}"
REPO=cse576-structured-poisoning
BRANCHES=(p1-pipelines p2-table-attacks p3-table-defense p4-renderer p5-gap2-defense)

git init -b main
git add .
git commit -m "[P1] repo skeleton: shared formats, harness, mock pipeline, per-person stubs and tests"

if [ "${SKIP_CREATE:-0}" != "1" ]; then
  gh repo create "$OWNER/$REPO" --private --source . --remote origin
else
  git remote add origin "https://github.com/$OWNER/$REPO.git"
fi
git push -u origin main
for b in "${BRANCHES[@]}"; do
  git branch "$b" main
  git push -u origin "$b"
done
echo
echo "Done. Next: add teammates as collaborators (Settings -> Collaborators),"
echo "protect main (Settings -> Branches: require PR + passing 'tests' check),"
echo "and fill in GitHub usernames in .github/CODEOWNERS."
