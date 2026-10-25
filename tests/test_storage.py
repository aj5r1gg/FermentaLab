import sqlite3
from contextlib import closing
import tempfile
import unittest

from pathlib import Path

from fermentalab.recipes import Recipe
from fermentalab.storage import (
    RecipeStore,
    StorageError,
)


def example_recipe():
    return Recipe.from_dict({
        "schema_version": 1,
        "id": "test-fermentation",
        "name": "Test Fermentation",
        "stages": [
            {
                "name": "Incubation",
                "duration_minutes": 480,
                "temperature_c": 40.0,
                "humidity_percent": None,
            }
        ],
    })


class TestRecipeStore(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = (
            Path(self.temp.name) / "fermentalab.db"
        )

        self.store = RecipeStore(self.database)
        self.store.initialise()

    def tearDown(self):
        self.temp.cleanup()

    def test_database_created(self):
        self.assertTrue(self.database.exists())

    def test_initialise_is_idempotent(self):
        self.store.initialise()
        self.store.initialise()

    def test_save_and_load_recipe(self):
        recipe = example_recipe()

        self.store.save_recipe(recipe)

        loaded = self.store.get_recipe(recipe.id)

        self.assertEqual(loaded, recipe)

    def test_missing_recipe(self):
        self.assertIsNone(
            self.store.get_recipe("missing")
        )

    def test_list_recipes(self):
        self.store.save_recipe(example_recipe())

        recipes = self.store.list_recipes()

        self.assertEqual(len(recipes), 1)
        self.assertEqual(
            recipes[0]["id"],
            "test-fermentation",
        )

    def test_recipe_update(self):
        original = example_recipe()

        self.store.save_recipe(original)

        modified = Recipe.from_dict({
            "schema_version": 1,
            "id": original.id,
            "name": "Updated Fermentation",
            "stages": [
                {
                    "name": "Updated Stage",
                    "duration_minutes": 600,
                    "temperature_c": 38.0,
                    "humidity_percent": 70.0,
                }
            ],
        })

        self.store.save_recipe(modified)

        self.assertEqual(
            self.store.get_recipe(original.id),
            modified,
        )

    def test_create_run(self):
        recipe = example_recipe()
        self.store.save_recipe(recipe)

        run_id = self.store.create_run(recipe.id)

        run = self.store.get_run(run_id)

        self.assertEqual(run["status"], "created")
        self.assertEqual(run["recipe"], recipe)
        self.assertIsNone(run["started_at"])

    def test_missing_run(self):
        self.assertIsNone(
            self.store.get_run("missing")
        )

    def test_run_requires_existing_recipe(self):
        with self.assertRaises(StorageError):
            self.store.create_run("missing")

    def test_run_snapshot_is_immutable(self):
        original = example_recipe()
        self.store.save_recipe(original)

        run_id = self.store.create_run(original.id)

        modified = Recipe.from_dict({
            "schema_version": 1,
            "id": original.id,
            "name": "Changed Recipe",
            "stages": [
                {
                    "name": "Changed Stage",
                    "duration_minutes": 120,
                    "temperature_c": 20.0,
                    "humidity_percent": None,
                }
            ],
        })

        self.store.save_recipe(modified)

        run = self.store.get_run(run_id)

        self.assertEqual(run["recipe"], original)
        self.assertEqual(
            self.store.get_recipe(original.id),
            modified,
        )

    def test_persistence_across_connections(self):
        recipe = example_recipe()

        self.store.save_recipe(recipe)

        second_store = RecipeStore(self.database)

        self.assertEqual(
            second_store.get_recipe(recipe.id),
            recipe,
        )

    def test_foreign_keys_enabled(self):
        with closing(self.store.connect()) as connection:
            with connection:
                enabled = connection.execute(
                    "PRAGMA foreign_keys"
                ).fetchone()[0]

        self.assertEqual(enabled, 1)

    def test_unsupported_schema_rejected(self):
        with closing(sqlite3.connect(self.database)) as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE metadata
                    SET value = '999'
                    WHERE key = 'schema_version'
                    """
                )

        with self.assertRaises(StorageError):
            self.store.initialise()


if __name__ == "__main__":
    unittest.main(verbosity=2)
