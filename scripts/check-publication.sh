#!/usr/bin/env bash

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

printf '\n===== FERMENTALAB PRE-PUBLICATION CHECK =====\n'

printf '\n===== 1. UNTRACKED PYTHON FILES =====\n'

UNTRACKED=()

while IFS= read -r -d '' file; do
    if [[ "$file" == *.py ]]; then
        UNTRACKED+=("$file")
    fi
done < <(
    git ls-files \
        --others \
        --exclude-standard \
        -z \
        -- app tests
)

if (( ${#UNTRACKED[@]} > 0 )); then
    printf '\nWARNING: Untracked Python files detected:\n\n'

    printf '  %s\n' "${UNTRACKED[@]}"

    printf '\nPublication check: FAILED\n'
    printf 'Review these files before publishing.\n'

    exit 1
fi

printf 'PASS: No untracked Python files.\n'

printf '\n===== 2. TRACKED FILE INTEGRITY =====\n'

if ! git diff --quiet -- app tests; then
    printf 'FAIL: Uncommitted application or test changes.\n'
    exit 1
fi

if ! git diff --cached --quiet -- app tests; then
    printf 'FAIL: Staged but uncommitted application or test changes.\n'
    exit 1
fi

printf 'PASS: Application and test files are committed.\n'

printf '\n===== 3. WHITESPACE INTEGRITY =====\n'

git diff --check HEAD

printf 'PASS: No whitespace errors in working changes.\n'

printf '\n===== RESULT =====\n'
printf 'PASS: Pre-publication checks completed.\n'
