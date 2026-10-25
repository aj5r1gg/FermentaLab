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


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        store = recipe_store(args.database)

        if args.command == "recipes":
            return list_recipes(store)

        if args.command == "simulate":
            return simulate(store, args)

        parser.error("Unknown command")

    except (
        ValueError,
        TypeError,
        sqlite3.Error,
        OSError,
    ) as exc:
        print(
            f"FermentaLab error: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
