# FermentaLab

**A local-first, Raspberry Pi–targeted food fermentation controller.**

FermentaLab is an experimental software and hardware project for controlling fermentation conditions inside a modified bar refrigerator. Development takes place on Ubuntu using Python and Docker Compose; the intended deployment platform is a Raspberry Pi.

The project focuses on programmable, relatively short food fermentations, including potential applications such as yogurt, fermented vegetables and tempeh. It is **not** a general-purpose preservation chamber, cheese-ageing cabinet, dehydrator or long-duration curing system.

## Project Status

**Experimental — under active development. No physical actuator operation has been qualified.**

The current implementation includes:

- Validated fermentation recipe models and multi-stage timing/environmental targets.
- SQLite recipe and fermentation-run persistence, transactional schema migrations and integrity verification.
- Run lifecycle management and interrupted-run recovery.
- Simulated temperature control, including hysteresis, proportional and PI approaches.
- A simulated three-node thermal model representing chamber air, vessel and food, with ambient heat exchange.
- Experimental temperature-control comparisons, mass-sensitivity diagnostics and finite-horizon predictive heating control.
- Simulated actuator authority, including generation-fenced tokens and supervisory safeguards.
- Automated regression tests and a Docker Compose development environment.

**Latest locally verified baseline: 252 passing tests (25 October 2026).** This is a recorded development result, not a guarantee that every future checkout or environment will produce the same result. GitHub Actions also runs regression tests on repository changes; its current status should be checked separately.

The software does **not** currently control physical heating, cooling or other electrical equipment. Simulation results do not establish real-world temperature accuracy, food safety or electrical safety.

## Temperature-Control Research

FermentaLab currently contains several **simulation-only** temperature-control implementations. The Step 39 corrected PI controller remains the benchmark; later controllers are experimental rather than qualified replacements.

| Development step | Purpose | Status |
| --- | --- | --- |
| 35–36 | Hysteresis, proportional and initial PI comparisons | Simulation research |
| 37–39 | PI diagnostics and corrected integral authority | **Step 39 retained as benchmark** |
| 40 | Thermal-mass sensitivity diagnostics | Reproducible simulation evidence |
| 41 | Mass-aware prediction-gain experiment | Not accepted as replacement; inconsistent performance |
| 42 | Finite-horizon predictive heating guard | Promising, experimental |
| 43 | Predictive-control robustness comparisons | Weak-heater regression identified |

In a six-hour simulated 42°C incubation, the Step 42 predictive heating guard reduced the **double-mass batch's last-hour mean absolute error** from **0.367°C (Step 39)** to **0.010°C**, without delaying first entry into the ±0.2°C band in that scenario. However, with a weak heater, the same guard worsened last-hour error from **0.058°C** to **0.224°C** and did not reach the target band during the six-hour run.

These numbers are results from an **unvalidated thermal model with idealised actuators**, not claims of hardware precision. The predictive controller must not be treated as the default physical controller on the basis of these simulations.

The next control-engineering work is to diagnose the weak-heater regression, distinguish controller limitations from physically insufficient heating capacity, and test predictive behaviour under additional model errors and disturbances.

## Safety

**Do not connect the current software to mains-powered heating or cooling equipment for unattended operation.**

The existing temperature controllers and actuator-authority components are simulation-only. Software authorisation tokens are not substitutes for independent electrical, thermal or hardware safety mechanisms.

Future physical operation requires appropriate hardware protection, commissioning, fault handling and verification. In particular, real refrigeration hardware will require compressor-safe switching and minimum on/off timing rather than the idealised fractional cooling used in simulations.

Food fermentation requires suitable sanitation, validated process conditions and food-specific safety practices. Aerobic, heat-generating fermentations such as tempeh will also require appropriate airflow and consideration of metabolic heat and internal food-temperature gradients.

Passing software tests does not establish food safety or electrical safety.

## Architecture

The current software implements recipe management, persistence, simulated temperature decisions and simulated actuator authority. Thermal simulations and controller comparisons operate as experimental analysis components, not as a qualified hardware-control path.

```text
Fermentation recipe and persisted run
                 |
                 v
Recipe stage and environmental targets
                 |
                 v
Simulation-only temperature control
  (hysteresis / proportional / PI;
   experimental predictive heating guard)
                 |
                 v
Simulated actuator authority and decisions
                 |
                 v
Simulated thermal plant (air / vessel / food)
                 |
                 +----> diagnostics and comparisons
```

These components are not yet integrated into a qualified physical control system. Persistent recipe and run data are managed using SQLite. The intended deployment architecture is local-first and does not require a cloud service for fundamental control functions.

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

FermentaLab uses a pinned checkout of the Open Fermentation Project for compatibility testing. The upstream project is separately licensed under GPL-3.0.

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

The regression suite uses an isolated temporary data directory to avoid modifying existing development data.

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

The latest locally verified development run completed **252 tests successfully**. The suite covers recipe validation, persistence, database migrations, schema integrity, run timing and lifecycle, upstream compatibility, simulated temperature control, simulated actuator authority, controller comparisons and robustness diagnostics.

## Run Simulation Comparisons

The following commands execute **simulations only**; they do not operate hardware:

```bash
docker compose run --rm --no-deps \
    fermentalab python -m fermentalab.mass_diagnostics

docker compose run --rm --no-deps \
    fermentalab python -m fermentalab.predictive_comparison

docker compose run --rm --no-deps \
    fermentalab python -m fermentalab.robustness_comparison
```

The results depend on the assumptions and limitations of the simulated thermal plant.

## Development Priorities

1. Diagnose predictive heating restrictions under weak-heater conditions.
2. Check heating-power feasibility and distinguish unreachable targets from control failures.
3. Extend predictive-control robustness tests, including thermal-model mismatch and disturbances.
4. Model fermentation-specific metabolic heat, airflow and food-temperature gradients where relevant.
5. Integrate and verify supervisory, sensing, fault-handling and stage-transition behaviour before any hardware connection.
6. Develop and commission physical interfaces with independent safety protection.

Physical actuator control is deliberately deferred.

## Upstream Acknowledgement

FermentaLab acknowledges Larry W Jordan Jr and contributors to the [Open Fermentation Project](https://github.com/Larouex/open-fermentation-project).

The original project is licensed under GPL-3.0. FermentaLab maintains a separate upstream reference checkout for compatibility testing.

See [NOTICE.md](NOTICE.md) for attribution and licensing details.

## Licence

Original FermentaLab source code is licensed under the **Mozilla Public License, Version 2.0**.

See [LICENSE](LICENSE). Third-party material retains its applicable licensing terms.
