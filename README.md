# FermentaLab

**Local-first, Raspberry Pi–targeted fermentation appliance — under development.**

FermentaLab is a single-chamber food-fermentation controller intended to use an existing compressor-driven bar refrigerator, supplementary heating, measured chamber conditions, and independent physical safety provisions. Development takes place on Ubuntu with Docker Compose; the intended appliance controller runs on Raspberry Pi/Linux.

> **Development status (26 October 2026): software qualification only.** The most recent locally reported qualification run passed **549 Python tests** and Ruff checks. These results do **not** demonstrate functioning Raspberry Pi hardware, physical actuator control, electrical safety, calibrated sensing, or fitness for unattended food production. Tests and status must be reverified against the checked-out commit.

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

The normal software controller is **not** the sole safety mechanism. Physical permission and thermal/electrical protection are separate domains that require independent implementation and qualification. An advisory heating or cooling decision is never, by itself, physical actuator authority.

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

### Quick start: inspect and qualify

From the repository root:

```bash
cd ~/projects/fermentalab
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
| `.github/workflows/tests.yml` | GitHub Actions test workflow |

Some exploratory controllers, comparisons, and diagnostics in the repository are **simulation-only** and must not be treated as approved hardware control implementations.

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

**Last reported local result:** 549 tests passed, Ruff passed (26 October 2026), following DS18B20 chamber-measurement integration. This is a historical report, not an assertion that CI has passed on GitHub.

The practical next sequence is:

1. Verify the actual hardware bill of materials, sensor selection, and safe wiring design against the existing specifications.
2. Obtain read-only measurements from a physically connected probe on the Raspberry Pi; verify identity, timestamps, calibration, failure modes, and placement.
3. Integrate the validated physical measurement path with supervision without activating heating or cooling.
4. Implement and qualify the independent permission and physical protection systems before any equipment switching.
5. Qualify actuator control, compressor restart/recovery behaviour, fault responses, and commissioning evidence under `FERM-MILE-001`.

The milestone specification—not the mere presence of code or a passing CI badge—determines acceptance.

## Continuous integration

A GitHub Actions workflow exists at `.github/workflows/tests.yml`. It runs checks on GitHub's environment; the local qualification wrapper may cover additional checks and may use a different container configuration. **Both results should be reviewed**, rather than assuming a CI success proves equivalence or physical safety.

A typical release-of-work procedure is:

```bash
./scripts/check.sh all
git diff --check
git status --short
# Review intended changes, then stage and commit them.
git push -u origin HEAD
```

Review the GitHub Actions run for the pushed commit. On failure, inspect the job log, repair the cause, rerun local qualification, and push a new corrective commit. Do not claim CI passed until GitHub reports success.

## Local control and contributions

FermentaLab is designed around **local operation and operator control**. Neither development nor production requires granting remote access to a coding assistant. Review changes before execution, preserve the existing architecture and engineering requirements, and do not commit unrelated files.

For development changes, use focused tests plus full qualification, clearly distinguish simulated behaviour from physical evidence, and keep additional dependencies justified by an actual hardware or engineering need.

## Licence

Consult the repository's actual licence file and accompanying notices for reuse terms. This README intentionally does not invent a licence or grant permissions that have not been established in the repository.
