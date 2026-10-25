# FermentaLab

**A local-first, Raspberry Pi–targeted food fermentation controller.**

FermentaLab is an experimental software and hardware project for
controlling fermentation conditions inside a modified bar refrigerator.

Development takes place on Ubuntu using Python and Docker Compose.
The intended deployment platform is a Raspberry Pi.

The project focuses on programmable, relatively short food fermentation
processes through controlled environmental conditions.

FermentaLab is not intended to be a general-purpose food preservation
chamber, cheese-ageing cabinet, dehydrator or long-duration curing system.

## Project Status

**Experimental — under active development.**

The current implementation includes:

- Validated fermentation recipe models.
- Multi-stage recipe timing and environmental targets.
- SQLite recipe and fermentation-run persistence.
- Transactional database schema migrations.
- Run lifecycle management.
- Interrupted-run recovery.
- Database schema and integrity verification.
- Simulated temperature control with hysteresis.
- Simulated actuator authority with generation-fenced tokens.
- Automated regression tests.
- Docker Compose development environment.

The software does not currently control physical heating, cooling or
other electrical equipment.

No physical actuator operation has been qualified.

## Safety

**Do not connect the current software to mains-powered heating or
cooling equipment for unattended operation.**

The existing temperature controller and actuator-authority components
are simulation-only.

Software authorisation tokens are not substitutes for independent
electrical, thermal or hardware safety mechanisms.

Future physical operation requires appropriate hardware protection,
commissioning, fault handling and verification.

Food fermentation requires suitable sanitation, validated process
conditions and food-specific safety practices.

Passing software tests does not establish food safety or electrical
safety.

## Architecture

The current software implements recipe management, persistence,
simulated temperature decisions and simulated actuator authority.

Conceptually:

```text
Fermentation recipe
        |
        v
Recipe stage and target selection
        |
        v
Simulated temperature controller
        |
        v
Simulated actuator authority
        |
        v
Simulated heating / cooling decisions
```

These components are not yet integrated into a qualified physical
control system.

Persistent recipe and run data are managed using SQLite.

The intended deployment architecture is local-first and does not
require a cloud service for fundamental control functions.

## Development Requirements

- Git
- Docker Engine
- Docker Compose plugin
- Access to the upstream reference repository for compatibility tests

## Clone FermentaLab

```bash
git clone https://github.com/aj5r1gg/FermentaLab.git
cd FermentaLab
```

## Retrieve the Upstream Reference

FermentaLab uses a pinned checkout of the Open Fermentation Project
for compatibility testing.

The upstream project is separately licensed under GPL-3.0.

```bash
mkdir -p upstream

git clone \
    https://github.com/Larouex/open-fermentation-project.git \
    upstream/open-fermentation-project

git -C upstream/open-fermentation-project \
    checkout --detach \
    "$(cat research/upstream-commit.txt)"
```

Verify the pinned revision:

```bash
EXPECTED="$(cat research/upstream-commit.txt)"

ACTUAL="$(
    git -C upstream/open-fermentation-project rev-parse HEAD
)"

test "$EXPECTED" = "$ACTUAL"
```

The upstream checkout is ignored by FermentaLab's Git repository.

## Build the Development Environment

```bash
docker compose build
```

The Docker Compose service uses:

- A read-only container filesystem.
- No container networking.
- No added Linux capabilities.
- No-new-privileges.
- A separately mounted, read-only upstream source tree.

This development configuration is not a production deployment.

## Run the Tests

The regression suite uses an isolated temporary data directory to
avoid modifying existing development data.

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

The established development baseline contains **138 passing tests**.

These cover recipe validation, persistence, database migrations,
schema integrity, run timing, run lifecycle, upstream compatibility,
simulated temperature control and simulated actuator authority.

GitHub Actions runs the regression suite on repository changes.

## Development Priorities

The next implementation priorities include:

1. Supervisory inhibition and watchdog behaviour.
2. Sensor freshness and validity handling.
3. Fault latching and controlled recovery.
4. Safe recipe-stage transitions.
5. Integration of simulated control components.
6. Subsequent hardware interfaces and commissioning.

Physical actuator control is deliberately deferred.

## Upstream Acknowledgement

FermentaLab acknowledges Larry W Jordan Jr and contributors to the
[Open Fermentation Project](https://github.com/Larouex/open-fermentation-project).

The original project is licensed under GPL-3.0.

FermentaLab maintains a separate upstream reference checkout for
compatibility testing.

See [NOTICE.md](NOTICE.md) for attribution and licensing details.

## Licence

Original FermentaLab source code is licensed under the
**Mozilla Public License, Version 2.0**.

See [LICENSE](LICENSE).

Third-party material retains its applicable licensing terms.
