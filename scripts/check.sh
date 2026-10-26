#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

MODE="${1:-all}"

case "$MODE" in
    all|lint|coverage)
        ;;
    *)
        echo "Usage: $0 [all|lint|coverage]" >&2
        exit 2
        ;;
esac

IMAGE="fermentalab:qualification"

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "Qualification image missing." >&2
    echo "Build it with:" >&2
    echo "docker compose build fermentalab" >&2
    echo "docker build -f docker/Dockerfile.qualification -t $IMAGE ." >&2
    exit 1
fi

DATA_DIR="$(mktemp -d)"
trap 'rm -rf -- "$DATA_DIR"' EXIT

DOCKER_ARGS=(
    run --rm
    --network none
    --read-only
    --security-opt no-new-privileges
    --cap-drop ALL
    --user "$(id -u):$(id -g)"
    --workdir /workspace
    --tmpfs /tmp:rw,noexec,nosuid,size=64m
    --env PYTHONDONTWRITEBYTECODE=1
    --env PYTHONPATH=/workspace/app:/workspace/upstream/software/src
    --env COVERAGE_FILE=/tmp/.coverage
    --env HYPOTHESIS_STORAGE_DIRECTORY=/tmp/hypothesis
    --volume "$PWD/app:/workspace/app:ro"
    --volume "$PWD/tests:/workspace/tests:ro"
    --volume "$DATA_DIR:/workspace/data"
    --volume "$PWD/upstream/open-fermentation-project/software/src:/workspace/upstream/software/src:ro"
)

run_lint() {
    echo
    echo "===== RUFF ====="

    timeout 60s docker "${DOCKER_ARGS[@]}" \
        "$IMAGE" \
        ruff check \
            --no-cache \
            --select E4,E7,E9,F \
            app tests
}

run_tests() {
    echo
    echo "===== REGRESSION TESTS ====="

    timeout 120s docker "${DOCKER_ARGS[@]}" \
        "$IMAGE" \
        python -m unittest discover \
            -s tests \
            -p 'test_*.py' \
            -q
}

run_coverage() {
    echo
    echo "===== BRANCH COVERAGE ====="

    timeout 120s docker "${DOCKER_ARGS[@]}" \
        "$IMAGE" \
        sh -c '
            python -m coverage run \
                --branch \
                --source=/workspace/app/fermentalab \
                -m unittest discover \
                -s tests \
                -p "test_*.py" \
                -q &&
            python -m coverage report -m
        '
}

case "$MODE" in
    all)
        run_lint
        run_tests
        ;;
    lint)
        run_lint
        ;;
    coverage)
        run_coverage
        ;;
esac

echo
echo "===== FERMENTALAB CHECKS PASSED ====="
