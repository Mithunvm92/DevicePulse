#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -n "$(git status --porcelain 2>/dev/null || true)" ]]; then :; fi
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "This folder is not a Git repository yet. Run: git init" >&2
  exit 1
fi
if [[ -f .env ]]; then echo "Refusing to continue: .env exists locally; confirm it is ignored and not staged."; fi
if git ls-files --error-unmatch .env >/dev/null 2>&1; then echo "ERROR: .env is tracked; remove it from Git before pushing." >&2; exit 1; fi
git status --short
echo "Review the status above. Then stage, commit, and push explicitly; this script does not push automatically."
