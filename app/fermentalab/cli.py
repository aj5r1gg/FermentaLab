"""
FermentaLab command-line interface.

Simulation and recipe inspection only.

No physical hardware control.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

from fermentalab.simulation_runner import SimulationRunner
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


def simulate(store, args):
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
