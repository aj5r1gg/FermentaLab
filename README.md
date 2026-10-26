# FermentaLab

**A Raspberry Pi–based controller for making fermented foods in a bar fridge.**

FermentaLab aims to turn an ordinary compressor-driven bar fridge, with supplementary heating, into a local, programmable fermentation chamber for foods such as **yoghurt and tempeh**. A recipe sets the target temperature and duration; the controller monitors the chamber and manages heating or cooling.

**Status: under development.** The software runs in simulation. A working Raspberry Pi appliance has **not** yet been built or safety-qualified.

## What works today

- Multi-stage fermentation recipes and run tracking.
- Temperature regulation, supervision and fault inhibition in software.
- Local SQLite run history and conservative recovery after interruptions.
- Simulated heating/cooling, including compressor minimum-OFF timing.
- DS18B20 temperature-sensor adapter, tested with simulated sensor inputs.
- Automated tests and GitHub Actions CI.

**Not yet working on physical hardware:** live Raspberry Pi sensor acquisition, relay control, physical compressor feedback, and independent electrical/thermal safety protection. None of the simulated results authorise switching a real heater or compressor.

## Get started (Ubuntu development)

You'll need Git and Docker with Docker Compose. The current development branch is **`main`**.

```bash
git clone https://github.com/aj5r1gg/FermentaLab.git
cd FermentaLab
```

The repository also uses a pinned upstream research checkout. If it isn't already present:

```bash
mkdir -p upstream
git clone https://github.com/Larouex/open-fermentation-project.git \
  upstream/open-fermentation-project
git -C upstream/open-fermentation-project checkout --detach \
  "$(cat research/upstream-commit.txt)"
```

Run the software checks:

```bash
./scripts/check.sh all
```

For coverage:

```bash
./scripts/check.sh coverage
```

The last reported local qualification on **26 October 2026** passed **549 Python tests and Ruff**. GitHub Actions passed on `main`, commit **`a23e361`** ([CI run](https://github.com/aj5r1gg/FermentaLab/actions/runs/40309505084)). These are software checks, **not physical appliance qualification**.

## Temperature-control research

The repository includes experimental simulation controllers alongside the normal software temperature controller. **Step 39's PI controller** remains the research benchmark; later predictive approaches have not been approved for hardware use.

In one simulated 42°C incubation, the Step 42 predictive approach improved last-hour temperature error from **0.367°C to 0.010°C** for a double-mass batch. It also performed worse with a weak heater (**0.058°C to 0.224°C**). These figures come from an unvalidated simulation—not a real fridge.

## Safety and next steps

FermentaLab's design requires normal Raspberry Pi control **plus independent actuator-permission and physical thermal/electrical protection**. The latter two are not yet implemented and qualified.

The next practical step is to connect and validate a real temperature probe on the Raspberry Pi **without operating the heater or compressor**. Hardware switching comes only after the independent protections are in place and tested.

## Engineering references

The project is governed by its existing specifications: **FERM-ARCH-001**, **FERM-CTRL-001**, **FERM-SAFE-001**, and **FERM-MILE-001**, alongside the product-editions specification and development roadmap. The README is an overview, not a substitute for those documents.

## Licence

Refer to the repository's licence file and notices for applicable terms; the licence has not been independently verified for this README.
