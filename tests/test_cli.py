import csv
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



    def test_csv_export(self):
        destination = (
            Path(self.directory.name) / "simulation.csv"
        )

        status, output, errors = self.run_cli(
            "simulate",
            "cli-test",
            "--ambient",
            "25",
            "--csv",
            str(destination),
        )

        self.assertEqual(status, 0)
        self.assertEqual(errors, "")
        self.assertTrue(destination.is_file())

        with destination.open(
            encoding="utf-8",
            newline="",
        ) as handle:
            rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 120)
        self.assertEqual(float(rows[-1]["elapsed_s"]), 600.0)
        self.assertEqual(
            float(rows[-1]["progress_percent"]),
            100.0,
        )

    def test_csv_refuses_overwrite(self):
        destination = (
            Path(self.directory.name) / "existing.csv"
        )

        destination.write_text(
            "DO NOT OVERWRITE",
            encoding="utf-8",
        )

        status, output, errors = self.run_cli(
            "simulate",
            "cli-test",
            "--ambient",
            "25",
            "--csv",
            str(destination),
        )

        self.assertEqual(status, 1)
        self.assertIn("File exists", errors)
        self.assertEqual(
            destination.read_text(encoding="utf-8"),
            "DO NOT OVERWRITE",
        )

    def test_csv_invalid_directory(self):
        destination = (
            Path(self.directory.name)
            / "missing"
            / "simulation.csv"
        )

        status, output, errors = self.run_cli(
            "simulate",
            "cli-test",
            "--ambient",
            "25",
            "--csv",
            str(destination),
        )

        self.assertEqual(status, 1)
        self.assertFalse(destination.exists())

    def test_csv_does_not_change_simulation_summary(self):
        destination = (
            Path(self.directory.name) / "comparison.csv"
        )

        first_status, first_output, _ = self.run_cli(
            "simulate",
            "cli-test",
            "--ambient",
            "38",
        )

        second_status, second_output, _ = self.run_cli(
            "simulate",
            "cli-test",
            "--ambient",
            "38",
            "--csv",
            str(destination),
        )

        self.assertEqual(first_status, 0)
        self.assertEqual(second_status, 0)

        for label in (
            "Minimum chamber:",
            "Maximum chamber:",
            "Final chamber:",
            "Final food:",
            "Heating time:",
            "Cooling time:",
            "Idle time:",
            "Progress:",
            "Status:",
        ):
            first_line = next(
                line for line in first_output.splitlines()
                if line.startswith(label)
            )

            second_line = next(
                line for line in second_output.splitlines()
                if line.startswith(label)
            )

            self.assertEqual(first_line, second_line)

    def test_exposure_valid_thresholds(self):
        status, output, errors = self.run_cli(
            "simulate",
            "cli-test",
            "--ambient",
            "38",
            "--exposure-min",
            "29",
            "--exposure-max",
            "31",
        )

        self.assertEqual(status, 0)
        self.assertEqual(errors, "")
        self.assertIn(
            "Temperature Exposure — Engineering Thresholds",
            output,
        )
        self.assertIn("29.000–31.000", output)
        self.assertIn("Excursions:", output)
        self.assertIn("COMPLETED", output)

    def test_exposure_defaults_to_food(self):
        status, output, errors = self.run_cli(
            "simulate",
            "cli-test",
            "--ambient",
            "38",
            "--exposure-min",
            "29",
            "--exposure-max",
            "31",
        )

        self.assertEqual(status, 0)
        self.assertEqual(errors, "")
        self.assertIn("Measurement:      food", output)

    def test_exposure_chamber_measurement(self):
        status, output, errors = self.run_cli(
            "simulate",
            "cli-test",
            "--ambient",
            "38",
            "--exposure-min",
            "29",
            "--exposure-max",
            "31",
            "--exposure-measurement",
            "chamber",
        )

        self.assertEqual(status, 0)
        self.assertEqual(errors, "")
        self.assertIn("Measurement:      chamber", output)

    def test_exposure_missing_minimum(self):
        status, output, errors = self.run_cli(
            "simulate",
            "cli-test",
            "--ambient",
            "38",
            "--exposure-max",
            "31",
        )

        self.assertEqual(status, 1)
        self.assertIn(
            "must be supplied together",
            errors,
        )

    def test_exposure_missing_maximum(self):
        status, output, errors = self.run_cli(
            "simulate",
            "cli-test",
            "--ambient",
            "38",
            "--exposure-min",
            "29",
        )

        self.assertEqual(status, 1)
        self.assertIn(
            "must be supplied together",
            errors,
        )

    def test_exposure_reversed_thresholds(self):
        status, output, errors = self.run_cli(
            "simulate",
            "cli-test",
            "--ambient",
            "38",
            "--exposure-min",
            "32",
            "--exposure-max",
            "28",
        )

        self.assertEqual(status, 1)
        self.assertIn(
            "minimum_c cannot exceed maximum_c",
            errors,
        )

    def test_exposure_optional(self):
        status, output, errors = self.run_cli(
            "simulate",
            "cli-test",
            "--ambient",
            "38",
        )

        self.assertEqual(status, 0)
        self.assertEqual(errors, "")
        self.assertNotIn(
            "Temperature Exposure — Engineering Thresholds",
            output,
        )
        self.assertIn("COMPLETED", output)


if __name__ == "__main__":
    unittest.main()
