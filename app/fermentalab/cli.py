"""
FermentaLab command-line interface.

Simulation and recipe inspection only.

No physical hardware control.
"""

import argparse
import csv
import os
import sqlite3
import sys
from pathlib import Path

from fermentalab.execution_coordinator import ExecutionCoordinator
from fermentalab.simulation_runner import SimulationRunner
from fermentalab.temperature_exposure import (
    analyse_temperature_exposure,
)
from fermentalab.storage import RecipeStore


DEFAULT_DATABASE = Path("/workspace/data/fermentalab.db")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="fermentalab",
        description=(
            "FermentaLab fermentation simulation tools"
        ),
    )

    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help="Path to existing FermentaLab SQLite database",
    )

    commands = parser.add_subparsers(
        dest="command",
        required=True,
    )

    commands.add_parser(
        "recipes",
        help="List stored fermentation recipes",
    )

    runs = commands.add_parser(
        "runs",
        help="List recent fermentation runs",
    )

    runs.add_argument(
        "--limit",
        type=int,
        default=50,
        metavar="N",
        help="Maximum runs to display (default: 50, maximum: 1000)",
    )

    run_info = commands.add_parser(
        "run-info",
        help="Inspect a persistent fermentation run",
    )

    run_info.add_argument(
        "run_id",
        help="ID of the fermentation run to inspect",
    )

    run_cancel = commands.add_parser(
        "run-cancel",
        help="Cancel a created or paused fermentation run",
    )

    run_cancel.add_argument(
        "run_id",
        help="ID of the fermentation run to cancel",
    )

    simulate = commands.add_parser(
        "simulate",
        help="Simulate a stored fermentation recipe",
    )

    simulate.add_argument(
        "recipe_id",
        help="ID of the recipe to simulate",
    )

    simulate.add_argument(
        "--ambient",
        type=float,
        required=True,
        help="Constant simulated ambient temperature in Celsius",
    )

    simulate.add_argument(
        "--initial",
        type=float,
        default=25.0,
        help="Initial chamber, vessel and food temperature",
    )

    simulate.add_argument(
        "--step",
        type=float,
        default=5.0,
        help="Simulation timestep in seconds (maximum 5)",
    )

    simulate.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Export simulation samples to a new CSV file",
    )

    simulate.add_argument(
        "--exposure-min",
        type=float,
        default=None,
        help="Minimum engineering exposure threshold in Celsius",
    )

    simulate.add_argument(
        "--exposure-max",
        type=float,
        default=None,
        help="Maximum engineering exposure threshold in Celsius",
    )

    simulate.add_argument(
        "--exposure-measurement",
        choices=("chamber", "vessel", "food"),
        default="food",
        help="Temperature measurement to analyse (default: food)",
    )

    run = commands.add_parser(
        "run",
        help="Execute a persistent fermentation simulation",
    )

    run.add_argument(
        "recipe_id",
        help="ID of the stored fermentation recipe",
    )

    run.add_argument(
        "--simulate",
        action="store_true",
        required=True,
        help="Explicitly select simulation-only execution",
    )

    run.add_argument(
        "--ambient",
        type=float,
        required=True,
        help="Simulated ambient temperature in Celsius",
    )

    run.add_argument(
        "--initial",
        type=float,
        default=25.0,
        help="Initial simulated temperature in Celsius",
    )

    run.add_argument(
        "--step",
        type=float,
        default=5.0,
        help="Simulation timestep in seconds (maximum 5)",
    )

    run.add_argument(
        "--report-every",
        type=float,
        default=15.0,
        metavar="MINUTES",
        help="Simulated minutes between progress reports (default: 15)",
    )

    return parser


def recipe_store(database_path):
    if not database_path.is_file():
        raise ValueError(
            f"Database does not exist: {database_path}"
        )

    return RecipeStore(database_path)


def list_recipes(store):
    recipes = store.list_recipes()

    print("FermentaLab — Stored Recipes")
    print()

    if not recipes:
        print("No recipes found.")
        return 0

    for recipe in recipes:
        print(
            f"{recipe['id']} — {recipe['name']}"
        )

    print()
    print(f"Total recipes: {len(recipes)}")

    return 0


def export_csv(result, destination):
    destination = Path(destination)

    # Exclusive creation prevents accidental overwriting.
    # The destination directory must already exist.
    created = False

    try:
        with destination.open(
            "x",
            encoding="utf-8",
            newline="",
        ) as output:
            created = True

            writer = csv.writer(output)

            writer.writerow([
                "elapsed_s",
                "ambient_c",
                "chamber_c",
                "vessel_c",
                "food_c",
                "progress_percent",
                "heating_permitted",
                "cooling_permitted",
            ])

            for sample in result.samples:
                writer.writerow([
                    sample.elapsed_s,
                    sample.ambient_c,
                    sample.chamber_c,
                    sample.vessel_c,
                    sample.food_c,
                    sample.progress_percent,
                    int(sample.heating_permitted),
                    int(sample.cooling_permitted),
                ])

    except Exception:
        if created:
            try:
                destination.unlink()
            except OSError:
                pass
        raise


def simulate(store, args):
    exposure_requested = (
        args.exposure_min is not None
        or args.exposure_max is not None
    )

    if exposure_requested and (
        args.exposure_min is None
        or args.exposure_max is None
    ):
        raise ValueError(
            "--exposure-min and --exposure-max must be supplied together"
        )

    recipe = store.get_recipe(args.recipe_id)

    if recipe is None:
        raise ValueError(
            f"Recipe not found: {args.recipe_id}"
        )

    runner = SimulationRunner(
        recipe,
        initial_c=args.initial,
        step_s=args.step,
    )

    result = runner.run(
        ambient_c=args.ambient,
    )

    exposure = None

    if exposure_requested:
        exposure = analyse_temperature_exposure(
            result.samples,
            measurement=f"{args.exposure_measurement}_c",
            minimum_c=args.exposure_min,
            maximum_c=args.exposure_max,
        )

    if args.csv is not None:
        export_csv(result, args.csv)

    final = result.samples[-1]

    print("FermentaLab — Fermentation Simulation")
    print()
    print(f"Recipe:           {recipe.name}")
    print(f"Recipe ID:        {recipe.id}")
    print(
        f"Duration:         "
        f"{recipe.total_duration_minutes / 60:.2f} hours"
    )
    print(f"Stages:           {len(recipe.stages)}")
    print(f"Ambient:          {args.ambient:.2f} °C")
    print(f"Initial:          {args.initial:.2f} °C")
    print()

    print("Simulation Results")
    print()
    print(
        f"Minimum chamber:  "
        f"{result.minimum_chamber_c:.3f} °C"
    )
    print(
        f"Maximum chamber:  "
        f"{result.maximum_chamber_c:.3f} °C"
    )
    print(
        f"Final chamber:    "
        f"{final.chamber_c:.3f} °C"
    )
    print(
        f"Final food:       "
        f"{final.food_c:.3f} °C"
    )
    print()

    print(
        f"Heating time:     "
        f"{result.heating_seconds / 3600:.3f} hours"
    )
    print(
        f"Cooling time:     "
        f"{result.cooling_seconds / 3600:.3f} hours"
    )
    print(
        f"Idle time:        "
        f"{result.idle_seconds / 3600:.3f} hours"
    )
    print()

    print(f"Progress:         {final.progress_percent:.1f}%")
    print(f"Status:           {result.state.value.upper()}")

    if args.csv is not None:
        print(f"CSV output:       {args.csv}")
        print(f"CSV data rows:    {len(result.samples)}")

    if exposure is not None:
        print()
        print("Temperature Exposure — Engineering Thresholds")
        print()
        print(f"Measurement:      {args.exposure_measurement}")
        print(
            f"Thresholds:       "
            f"{exposure.minimum_c:.3f}–{exposure.maximum_c:.3f} °C"
        )
        print(
            f"Observed minimum: {exposure.observed_minimum_c:.3f} °C"
        )
        print(
            f"Observed maximum: {exposure.observed_maximum_c:.3f} °C"
        )
        print(
            f"Below range:      "
            f"{exposure.below_seconds / 3600:.3f} hours"
        )
        print(
            f"Within range:     "
            f"{exposure.within_seconds / 3600:.3f} hours"
        )
        print(
            f"Above range:      "
            f"{exposure.above_seconds / 3600:.3f} hours"
        )
        print(f"Excursions:       {exposure.excursion_count}")
        print(
            f"Longest:          "
            f"{exposure.longest_excursion_seconds / 60:.2f} minutes"
        )
        print()
        print(
            "Engineering thresholds only — "
            "not qualified food-safety limits."
        )

    print()
    print(
        "SIMULATION ONLY — illustrative thermal model; "
        "no physical compressor scheduling or safety validation."
    )

    return 0


def cancel_fermentation_run(store, args):
    """
    Cancel a non-running persistent fermentation run.

    This CLI has no ownership of an active controller.
    It must never cancel a RUNNING record directly.
    """
    run = store.get_run(args.run_id)

    if run is None:
        raise ValueError(
            f"Fermentation run not found: {args.run_id}"
        )

    if run["status"] not in ("created", "paused"):
        raise ValueError(
            "CLI cancellation requires a created or paused run; "
            f"current status is {run['status']}"
        )

    # The storage layer performs the terminal transition
    # atomically. This interface is simulation-only and
    # does not control physical actuators.
    cancelled = store.transition_run(
        args.run_id,
        "cancel",
        allowed_from=("created", "paused"),
    )

    print("FermentaLab — Fermentation Run Cancelled")
    print()
    print(f"Run ID:    {cancelled['id']}")
    print(f"Recipe:    {cancelled['recipe_id']}")
    print(f"Status:    {cancelled['status'].upper()}")
    print(f"Ended:     {cancelled['ended_at']}")
    print()
    print(
        "Persistent lifecycle updated. "
        "No physical actuator control was performed."
    )

    return 0


def inspect_fermentation_run(store, args):
    run = store.get_run(args.run_id)

    if run is None:
        raise ValueError(
            f"Fermentation run not found: {args.run_id}"
        )

    recipe = run["recipe"]

    print("FermentaLab — Fermentation Run")
    print()

    fields = (
        ("Run ID", run["id"]),
        ("Status", run["status"].upper()),
        ("Recipe ID", run["recipe_id"]),
        ("Recipe name", recipe.name),
        ("Created", run["created_at"]),
        ("Started", run["started_at"]),
        ("Paused", run["paused_at"]),
        ("Completed", run["completed_at"]),
        ("Ended", run["ended_at"]),
        ("Running since", run["running_since"]),
        ("Elapsed seconds", run["elapsed_seconds"]),
        ("Elapsed microseconds", run["elapsed_microseconds"]),
        ("Failure reason", run["failure_reason"]),
    )

    for label, value in fields:
        print(
            f"{label + ':':<23}"
            f"{value if value is not None else '—'}"
        )

    print()
    print("Recipe Snapshot")
    print("-" * 60)

    for number, stage in enumerate(recipe.stages, 1):
        print()
        print(f"Stage {number}: {stage.name}")
        print(f"  Duration:    {stage.duration_minutes} minutes")
        print(f"  Temperature: {stage.temperature_c:.2f} °C")

        if stage.humidity_percent is None:
            print("  Humidity:    Not controlled")
        else:
            print(
                f"  Humidity:    "
                f"{stage.humidity_percent:.1f}%"
            )

    print()
    print(
        "Elapsed time represents actual recorded execution "
        "time, not simulated fermentation duration."
    )

    return 0


def list_fermentation_runs(store, args):
    runs = store.list_runs(limit=args.limit)

    print("FermentaLab — Fermentation Runs")
    print()

    if not runs:
        print("No fermentation runs recorded.")
        return 0

    print(
        f"{'RUN ID':<36}  "
        f"{'STATUS':<11}  "
        f"RECIPE"
    )
    print("-" * 90)

    for run in runs:
        print(
            f"{run['id']:<36}  "
            f"{run['status']:<11}  "
            f"{run['recipe_id']}"
        )

    print()
    print(f"Total displayed: {len(runs)}")

    return 0


def format_simulation_time(elapsed_s):
    total_minutes = int(round(elapsed_s / 60.0))
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02d}:{minutes:02d}"


def print_simulation_observation(observation):
    if observation.state.value == "completed":
        control = "OFF"
    elif observation.heating_permitted:
        control = "HEATING"
    elif observation.cooling_permitted:
        control = "COOLING"
    else:
        control = "IDLE"

    target = (
        f"{observation.target_c:.1f}"
        if observation.target_c is not None
        else "—"
    )

    print(
        f"{format_simulation_time(observation.elapsed_s):>8}  "
        f"{observation.stage_name[:16]:<16}  "
        f"{observation.chamber_c:>7.2f}  "
        f"{target:>7}  "
        f"{control:<8}  "
        f"{observation.progress_percent:>7.1f}%"
    )


def run_persistent_simulation(store, args):
    """
    Execute a stored recipe through the persistent coordinator.

    Simulation only. No physical actuator control.
    """
    recipe = store.get_recipe(args.recipe_id)

    if recipe is None:
        raise ValueError(
            f"Recipe not found: {args.recipe_id}"
        )

    if (
        args.report_every <= 0
        or not 0 < args.report_every < float("inf")
    ):
        raise ValueError(
            "--report-every must be finite and greater than zero"
        )

    # Validate simulation configuration before creating
    # a persistent fermentation run.
    runner = SimulationRunner(
        recipe,
        initial_c=args.initial,
        step_s=args.step,
    )

    run_id = store.create_run(recipe.id)

    coordinator = ExecutionCoordinator(
        store=store,
        run_id=run_id,
    )

    print("FermentaLab — Persistent Fermentation Simulation")
    print()
    print(f"Recipe:           {recipe.name}")
    print(f"Recipe ID:        {recipe.id}")
    print(f"Run ID:           {run_id}")
    print(f"Ambient:          {args.ambient:.2f} °C")
    print()

    print(
        "SIM TIME  STAGE             CHAMBER   TARGET  "
        "CONTROL   PROGRESS"
    )
    print("-" * 72)

    result = runner.run(
        ambient_c=args.ambient,
        coordinator=coordinator,
        observer=print_simulation_observation,
        report_every_s=args.report_every * 60.0,
    )

    print()

    stored_run = store.get_run(run_id)

    final = result.samples[-1]

    print("Execution Results")
    print()
    print(f"Status:           {stored_run['status'].upper()}")
    print(f"Progress:         {final.progress_percent:.1f}%")
    print(
        f"Minimum chamber:  "
        f"{result.minimum_chamber_c:.3f} °C"
    )
    print(
        f"Maximum chamber:  "
        f"{result.maximum_chamber_c:.3f} °C"
    )
    print(
        f"Final chamber:    "
        f"{final.chamber_c:.3f} °C"
    )
    print(
        f"Final food:       "
        f"{final.food_c:.3f} °C"
    )
    print(
        f"Heating time:     "
        f"{result.heating_seconds / 3600:.3f} hours"
    )
    print(
        f"Cooling time:     "
        f"{result.cooling_seconds / 3600:.3f} hours"
    )
    print(
        f"Idle time:        "
        f"{result.idle_seconds / 3600:.3f} hours"
    )
    print()
    print(
        "SIMULATION ONLY — no physical actuator control "
        "or food-safety qualification."
    )

    return 0


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        store = recipe_store(args.database)

        if args.command == "recipes":
            return list_recipes(store)

        if args.command == "runs":
            return list_fermentation_runs(store, args)

        if args.command == "run-info":
            return inspect_fermentation_run(store, args)

        if args.command == "run-cancel":
            return cancel_fermentation_run(store, args)




        if args.command == "simulate":
            return simulate(store, args)

        if args.command == "run":
            return run_persistent_simulation(store, args)

        parser.error("Unknown command")

    except (
        ValueError,
        TypeError,
        sqlite3.Error,
        RuntimeError,
        OSError,
    ) as exc:
        print(
            f"FermentaLab error: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
