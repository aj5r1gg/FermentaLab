import io
import tempfile
import unittest

from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from fermentalab.cli import main
from fermentalab.recipes import Recipe
from fermentalab.storage import RecipeStore


class TestFermentaLabCLI(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()

        self.database = (
            Path(self.directory.name) / "fermentalab.db"
        )

        self.store = RecipeStore(self.database)
        self.store.initialise()

        self.store.save_recipe(
            Recipe.from_dict({
                "schema_version": 1,
                "id": "cli-test",
                "name": "CLI Test Recipe",
                "stages": [
                    {
                        "name": "Fermentation",
                        "duration_minutes": 10,
                        "temperature_c": 30.0,
                        "humidity_percent": None,
                    },
                ],
            })
        )

    def tearDown(self):
        self.directory.cleanup()

    def run_cli(self, *arguments):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = main([
                "--database",
                str(self.database),
                *arguments,
            ])

        return status, stdout.getvalue(), stderr.getvalue()

    def test_list_recipes(self):
        status, output, errors = self.run_cli(
            "recipes"
        )

        self.assertEqual(status, 0)
        self.assertIn("cli-test", output)
        self.assertIn("CLI Test Recipe", output)
        self.assertEqual(errors, "")

    def test_simulate_recipe(self):
        status, output, errors = self.run_cli(
            "simulate",
            "cli-test",
            "--ambient",
            "25",
        )

        self.assertEqual(status, 0)
        self.assertIn("COMPLETED", output)
        self.assertIn("100.0%", output)
        self.assertEqual(errors, "")

    def test_unknown_recipe(self):
        status, output, errors = self.run_cli(
            "simulate",
            "does-not-exist",
            "--ambient",
            "25",
        )

        self.assertEqual(status, 1)
        self.assertIn("Recipe not found", errors)

    def test_missing_database(self):
        missing = (
            Path(self.directory.name) / "missing.db"
        )

        stdout = io.StringIO()
        stderr = io.StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = main([
                "--database",
                str(missing),
                "recipes",
            ])

        self.assertEqual(status, 1)
        self.assertIn("Database does not exist", stderr.getvalue())

    def test_invalid_step(self):
        status, output, errors = self.run_cli(
            "simulate",
            "cli-test",
            "--ambient",
            "25",
            "--step",
            "10",
        )

        self.assertEqual(status, 1)
        self.assertIn("step_s", errors)


if __name__ == "__main__":
    unittest.main()
