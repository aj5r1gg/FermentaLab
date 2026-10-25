# Contributing to FermentaLab

FermentaLab welcomes technically sound contributions.

## Development Principles

- Preserve local-first operation.
- Keep hardware safety separate from ordinary application logic.
- Do not introduce physical actuator operation without the required
  safety architecture and verification.
- Preserve deterministic, testable behaviour.
- Add regression tests for functional changes.
- Avoid unnecessary dependencies.
- Preserve compatibility with the intended Raspberry Pi platform.
- Keep changes focused and reviewable.

## Development Setup

Follow the instructions in [README.md](README.md).

## Testing

Run the full regression suite using an isolated data directory:

```bash
TEST_DATA_DIR="$(mktemp -d)" || exit 1

docker compose run --rm --no-deps \
    --volume "$TEST_DATA_DIR:/workspace/data" \
    fermentalab \
    python -m unittest discover \
        -s tests \
        -p 'test_*.py' \
        -v

TEST_RESULT=$?

rm -rf -- "$TEST_DATA_DIR"

test "$TEST_RESULT" -eq 0
```

## Pull Requests

Include:

- The problem being addressed.
- A description of the implementation.
- Tests added or updated.
- Any implications for control or safety behaviour.
- Any third-party source or licensing considerations.

## Licensing

By contributing, you agree that your original contribution may be
distributed under MPL-2.0.

Do not submit code copied from another project unless its licence
permits the proposed use and its attribution requirements are met.

Upstream GPL-3.0 code must not be silently relicensed as MPL-2.0.
