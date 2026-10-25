"""Acceptance tests for FermentaLab schema v3."""

import sqlite3
import tempfile
import unittest

from contextlib import closing
from pathlib import Path

from fermentalab.storage import RecipeStore
from fermentalab.recipes import Recipe


class TestSchemaV3(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.database = (
            Path(self.temp.name) / "fermentalab.db"
        )

        self.store = RecipeStore(self.database)

    def version(self):
        with closing(
            sqlite3.connect(self.database)
        ) as connection:
            return connection.execute(
                """
                SELECT value
                FROM metadata
                WHERE key = 'schema_version'
                """
            ).fetchone()[0]

    def columns(self):
        with closing(
            sqlite3.connect(self.database)
        ) as connection:
            return {
                row[1]: row
                for row in connection.execute(
                    "PRAGMA table_info(fermentation_runs)"
                )
            }

    def example_recipe(self):
        return Recipe.from_dict({
            "schema_version": 1,
            "id": "schema-v3-test",
            "name": "Schema V3 Test",
            "stages": [
                {
                    "name": "Incubation",
                    "duration_minutes": 120,
                    "temperature_c": 35.0,
                    "humidity_percent": None,
                }
            ],
        })

    def test_new_database_uses_v3(self):
        self.store.initialise()

        self.assertEqual(self.version(), "3")

    def test_microsecond_column_exists(self):
        self.store.initialise()

        self.assertIn(
            "elapsed_microseconds",
            self.columns(),
        )

    def test_microsecond_column_is_integer(self):
        self.store.initialise()

        column = self.columns()["elapsed_microseconds"]

        self.assertEqual(column[2].upper(), "INTEGER")
        self.assertEqual(column[3], 1)
        self.assertEqual(column[4], "0")

    def test_new_run_starts_at_zero(self):
        self.store.initialise()

        recipe = self.example_recipe()
        self.store.save_recipe(recipe)

        run_id = self.store.create_run(recipe.id)
        run = self.store.get_run(run_id)

        self.assertEqual(
            run["elapsed_microseconds"],
            0,
        )

        self.assertEqual(
            run["elapsed_seconds"],
            0,
        )

    def test_negative_microseconds_rejected(self):
        self.store.initialise()

        recipe = self.example_recipe()
        self.store.save_recipe(recipe)

        run_id = self.store.create_run(recipe.id)

        with self.assertRaises(
            sqlite3.IntegrityError
        ):
            with self.store.transaction() as connection:
                connection.execute(
                    """
                    UPDATE fermentation_runs
                    SET elapsed_microseconds = -1
                    WHERE id = ?
                    """,
                    (run_id,),
                )

    def test_v3_initialisation_is_idempotent(self):
        self.store.initialise()
        self.store.initialise()
        self.store.initialise()

        self.assertEqual(self.version(), "3")

    def test_v3_preserves_recipe_snapshot(self):
        self.store.initialise()

        recipe = self.example_recipe()
        self.store.save_recipe(recipe)

        run_id = self.store.create_run(recipe.id)

        self.assertEqual(
            self.store.get_run(run_id)["recipe"],
            recipe,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
