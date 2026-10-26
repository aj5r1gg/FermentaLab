# FermentaLab

**Local-first, Raspberry Pi–targeted fermentation appliance — under development.**

FermentaLab is a single-chamber food-fermentation controller intended to use an existing compressor-driven bar refrigerator, supplementary heating, measured chamber conditions, and independent physical safety provisions. Development takes place on Ubuntu with Docker Compose; the intended appliance controller runs on Raspberry Pi/Linux.

> **Development status (26 October 2026): software qualification only.** Local qualification was reported as **549 Python tests passing and Ruff passing**. GitHub Actions **FermentaLab Tests** succeeded on `development-history` at commit **`04ce178`** ([run 40307278692](https://github.com/aj5r1gg/FermentaLab/actions/runs/40307278692)). The GitHub run verifies its Python regression job; it is **not** evidence of physical commissioning, calibrated sensors, safe actuator switching, electrical safety, or unattended food-production suitability. These results are historical and commit-specific; this README revision itself has not yet been run through CI.

## Scope

FermentaLab is designed for **relatively short fermentation programmes**. It is not a general food-preservation chamber. Cheese ageing, meat curing, dehydration, pressure processing, and long-duration preservation are outside the agreed scope.

The initial objective is a dependable local fermentation appliance. Future product editions and optional integrations must not delay qualification of the initial appliance.

## Architecture at a glance

```text
Fermentation recipe / lifecycle
             │
             ▼
      Runtime and supervisor
             │
             ▼
      Control decisions
             │
             ▼
  Command admission and ownership
             │
             ▼
      Hardware adapter (future)
             │
             ▼
   Heating / cooling equipment

Primary sensor → measurement validation → supervisor

Independent actuator-permission protection (physical: pending)
Independent thermal/electrical protection (physical: pending)
```

The specification identifies three independent safety domains: **A — normal Pi control**, **B — independent timed actuator permission**, and **C — independent physical thermal/electrical cutoff**. Domains B and C are not established by the present software. The normal software controller is **not** the sole safety mechanism. An advisory heating or cooling decision is never, by itself, physical actuator authority.

## Implemented software

The repository contains work on:

- Recipe-driven fermentation runtime and stage/lifecycle handling.
- Temperature-control decisions and supervisory fault handling.
- Command admission, execution identity, inhibition, and ownership checks.
- Local SQLite persistence and conservative interrupted-run recovery.
- Deterministic thermal simulation, diagnostics, and qualification tests.
- Software-only compressor minimum-OFF protection, including clock-fault latching and optional integration with the simulation runner.
- A DS18B20 acquisition adapter and chamber-reading integration, with tests based on injected sensor doubles.
- Simulated chamber and environmental measurement representations, including optional monitoring measurements.

**Not yet demonstrated:** a connected DS18B20 on a Raspberry Pi, end-to-end physical temperature acquisition into authorised control, real relays/actuators, compressor feedback, process-restart physical-state reconciliation, independent protective circuits, and physical commissioning. The optional `w1thermsensor` Python library is imported only when physical sensor discovery is requested; the isolated Ubuntu tests do not need a connected probe.

The DS18B20 is a **provisional sensor candidate**, not a qualified authoritative sensor. Sensor selection, placement, calibration, detection of failure, and environmental suitability remain subject to engineering verification.

## Development environment

- **Development host:** Ubuntu Desktop.
- **Qualification:** Docker Compose and the existing `scripts/check.sh` wrapper.
- **Application:** Python, with a local SQLite persistence layer.
- **Target:** Raspberry Pi/Linux, subject to hardware integration and qualification.
- **Operation:** Local-first; the initial appliance does not depend on cloud connectivity.

The project's Docker environment is intended for software development and reproducible qualification. It does not grant permission to operate physical actuators.

### Fresh Ubuntu checkout

Prerequisites: Git, Docker Engine with Compose (`docker compose`), Bash, and permission to use Docker. The GitHub CLI (`gh`) is optional and only needed for inspecting or manually dispatching CI.

```bash
git clone https://github.com/aj5r1gg/FermentaLab.git
cd FermentaLab
git switch development-history
```

The current GitHub workflow also uses a pinned research checkout of the upstream Open Fermentation Project. If `upstream/open-fermentation-project` is absent, establish it at the recorded commit before running checks that require it:

```bash
mkdir -p upstream
git clone https://github.com/Larouex/open-fermentation-project.git \
    upstream/open-fermentation-project
git -C upstream/open-fermentation-project checkout --detach \
    "$(cat research/upstream-commit.txt)"
test "$(git -C upstream/open-fermentation-project rev-parse HEAD)" = \
    "$(cat research/upstream-commit.txt)"
```

Do not overwrite an existing upstream checkout; inspect it first. Upstream code is a research reference, not an approved actuator controller.

Build the development image with `docker compose build`. The development image installs `hypothesis==6.170.11`, used by the sensor fault-injection tests; `docker/Dockerfile.qualification` separately provides Ruff, Coverage and Hypothesis for local qualification. These are **different image configurations**.

### Quick start: inspect and qualify

From the repository root (whether freshly cloned or already checked out):

```bash
./scripts/check.sh all
```

The command runs the project's configured software checks. A successful run should end with `FERMENTALAB CHECKS PASSED`; use the actual result rather than the historical count in this README.

Coverage, when needed:

```bash
./scripts/check.sh coverage
```

For a log that avoids flooding the terminal:

```bash
mkdir -p "$HOME/Documents/FermentaLab"
./scripts/check.sh all > "$HOME/Documents/FermentaLab/qualification.log" 2>&1
result=$?
tail -25 "$HOME/Documents/FermentaLab/qualification.log"
printf 'Exit status: %s\n' "$result"
```

Do not run hardware-dependent code in the development container on the assumption that passing simulated tests qualifies real equipment.

### Selected source areas

| Location | Responsibility |
| --- | --- |
| `app/fermentalab/actuator_authority.py` | Software actuator authority tokens |
| `app/fermentalab/temperature_control.py` | Temperature regulation decisions |
| `app/fermentalab/supervisor.py` | Supervision and inhibition |
| `app/fermentalab/fermentation_runtime.py` | Fermentation programme runtime |
| `app/fermentalab/execution_coordinator.py` | Runtime/persistent lifecycle coordination |
| `app/fermentalab/storage.py` | Local SQLite persistence |
| `app/fermentalab/command_admission.py` | Simulated command admission and revalidation |
| `app/fermentalab/hardware_owner.py` | Cooperative hardware-ownership coordination |
| `app/fermentalab/compressor_guard.py` | Software-only minimum-OFF timing guard |
| `app/fermentalab/compressor_command.py` | Simulated command/timing composition |
| `app/fermentalab/simulation_runner.py` | Deterministic software simulation |
| `app/fermentalab/sensors.py` | Existing measurement data contracts |
| `app/fermentalab/ds18b20_reader.py` | Optional DS18B20 acquisition and reading adapter |
| `tests/` | Automated software tests |
| `scripts/check.sh` | Local qualification entry point |
| `compose.yaml` and `docker/Dockerfile` | Development container configuration |
| `docker/Dockerfile.qualification` | Local qualification image |
| `research/upstream-commit.txt` | Pinned upstream source revision |
| `.github/workflows/tests.yml` | GitHub Actions test workflow |

Some exploratory controllers, comparisons, and diagnostics in the repository are **simulation-only** and must not be treated as approved hardware control implementations. Historical research material may differ between `main` and `development-history`; this README preserves the supplied Steps 35–43 results, but has not been checked against the entire `main` README.

## Temperature-Control Research

FermentaLab contains several **simulation-only** temperature-control implementations. The corrected Step 39 PI controller remains the **research benchmark**; subsequent controllers are experimental and have **not** been qualified as replacements for the normal hardware controller. The implemented `temperature_control.py` remains the established software temperature-demand path.

| Development step | Purpose | Status |
| --- | --- | --- |
| 35–36 | Hysteresis, proportional and initial PI comparisons | Simulation research |
| 37–39 | PI diagnostics and corrected integral authority | **Step 39 retained as benchmark** |
| 40 | Thermal-mass sensitivity diagnostics | Reproducible simulation evidence |
| 41 | Mass-aware prediction-gain experiment | Not accepted as replacement; inconsistent performance |
| 42 | Finite-horizon predictive heating guard | Promising, experimental |
| 43 | Predictive-control robustness comparisons | Weak-heater regression identified |

In a six-hour simulated **42°C** incubation, the Step 42 predictive heating guard reduced the double-mass batch's **last-hour mean absolute error from 0.367°C (Step 39) to 0.010°C**, without delaying first entry into the **±0.2°C** band in that scenario. Under the weak-heater scenario, however, the same guard **worsened last-hour error from 0.058°C to 0.224°C** and failed to reach the target band within six hours.

These are results of an **unvalidated thermal model with idealised actuators**, **not** demonstrated hardware precision. The predictive controller must not be made the default physical controller on the basis of these simulations. Proposed further research is to distinguish controller limitations from insufficient heater capacity and test predictive behaviour against additional model error and disturbances. This research does not supersede physical measurement and safety qualification.

## Engineering and safety boundaries

1. **A measurement is not authority.** A sensor reading requires validation, freshness checking, and the applicable qualification before use for control.
2. **A demand is not permission.** Temperature demand cannot override command admission, ownership, fault inhibition, or independent safety domains.
3. **OFF must remain available.** Invalid identity, lost ownership, stale state, or failed supervision must not result in a newly authorised ON command.
4. **Compressors need protection.** Minimum-OFF timing in simulation does not, by itself, protect a real compressor across power loss, process restart, hardware-state uncertainty, or relay failure.
5. **Safety must not depend on the Pi alone.** Independent actuator-permission and physical thermal/electrical protection require construction and evidence-based acceptance.
6. **Software qualification is not commissioning.** Never connect or energise mains switching, heaters, or refrigeration hardware merely because unit tests pass.

The actual physical hardware design and release decisions are governed by the engineering specifications, not by this README.

## Engineering documents

The normative engineering baseline comprises four principal specifications:

| ID | Document | Current working version |
| --- | --- | --- |
| `FERM-ARCH-001` | System Architecture Specification | v0.3 |
| `FERM-CTRL-001` | Control Engineering Specification | v0.4 |
| `FERM-SAFE-001` | Electrical, Thermal and Physical Safety Specification | v0.2 |
| `FERM-MILE-001` | Milestone and Acceptance Specification | v0.2 |

Additional product/planning documents:

| ID | Document | Version and role |
| --- | --- | --- |
| `FERM-PROD-001` | Product Editions and Feature Entitlement Specification | v0.3; product specification, draft |
| `FERM-ROAD-001` | Development Roadmap | v0.2; non-normative planning document |

The specifications establish requirements and acceptance obligations; README summaries cannot supersede them. Draft status and hardware-dependent acceptance limitations remain applicable.

## Current qualification and next milestones

**Recorded results (26 October 2026):** 549 Python tests and Ruff passed locally. GitHub Actions run [40307278692](https://github.com/aj5r1gg/FermentaLab/actions/runs/40307278692) completed successfully on commit `04ce178` (`development-history`). The earlier CI run on `09c3ac5` failed at test discovery because the development image lacked Hypothesis; commit `ce741df` added that dependency. Each result is specific to its commit and environment. The GitHub workflow does not establish that local Ruff checks ran in CI.

The practical next sequence is:

1. Verify the actual hardware bill of materials, sensor selection, and safe wiring design against the existing specifications.
2. Obtain read-only measurements from a physically connected probe on the Raspberry Pi; verify identity, timestamps, calibration, failure modes, and placement.
3. Integrate the validated physical measurement path with supervision without activating heating or cooling.
4. Implement and qualify the independent permission and physical protection systems before any equipment switching.
5. Qualify actuator control, compressor restart/recovery behaviour, fault responses, and commissioning evidence under `FERM-MILE-001`.

The milestone specification—not the mere presence of code or a passing CI badge—determines acceptance.

## Continuous integration

The active **FermentaLab Tests** workflow is at `.github/workflows/tests.yml`. Its Python regression suite passed in [run 40307278692](https://github.com/aj5r1gg/FermentaLab/actions/runs/40307278692) on `development-history` (`04ce178`). The repository default branch is `main`; the recorded run was triggered using `workflow_dispatch`. Local `scripts/check.sh all` also runs Ruff and is a separate qualification path. **Review both results**: GitHub CI success is neither identical to full local qualification nor evidence of physical safety.

With `gh` installed and authenticated, inspect or manually trigger the workflow:

```bash
gh run list --workflow tests.yml --branch development-history --limit 5
gh workflow run tests.yml --ref development-history
# Then retrieve the new run ID and check its commit and conclusion.
```

A successful dispatch request only means the event was accepted. Confirm the run has actually completed with `success`.

A typical release-of-work procedure is:

```bash
./scripts/check.sh all
git diff --check
git status --short
# Review intended changes, then stage and commit them.
git push -u origin HEAD
```

Review the GitHub Actions run for the pushed commit. On failure, inspect the job log, repair the cause, rerun local qualification, and push a new corrective commit. Do not claim CI passed until GitHub reports success.

## Configuration and physical deployment status

The existing runtime provides recipe stages, local SQLite lifecycle persistence and conservative recovery of interrupted runs. The exact production CLI commands, database file locations, environment-variable catalogue, installed recipe paths and Raspberry Pi service/deployment procedure have **not been verified from the repository configuration for this revision**. They are not documented here as stable interfaces. Refer to the actual CLI, storage and Compose configuration before selecting paths or running production commands.

The DS18B20 adapter can produce an existing `ChamberTemperatureReading` containing sensor identity, temperature and a monotonic timestamp. Its tests inject simulated sensor objects. The optional `w1thermsensor` dependency and real probe have not been commissioned on Raspberry Pi. This path is not yet wired as a qualified, authoritative physical measurement path into actuation.

No Raspberry Pi production deployment, real power switching, or independent safety commissioning procedure is supplied by the currently verified software. Do not substitute this development README for the physical engineering specifications.

## Local control and contributions

FermentaLab is designed around **local operation and operator control**. Neither development nor production requires granting remote access to a coding assistant. Review changes before execution, preserve the existing architecture and engineering requirements, and do not commit unrelated files.

For development changes, use focused tests plus full qualification, clearly distinguish simulated behaviour from physical evidence, and keep additional dependencies justified by an actual hardware or engineering need.

## Licence

The licence has **not been verified** from a repository licence file in the materials reviewed for this revision. Check the actual root `LICENSE`/`COPYING` file and applicable notices before reuse or redistribution. This README does not grant rights or assume a licence.
