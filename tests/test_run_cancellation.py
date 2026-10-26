"""
FermentaLab controlled cancellation acceptance tests.

These tests exercise persistent lifecycle semantics only.
No physical hardware or actuator authority is involved.
"""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fermentalab.cli import cancel_fermentation_run
from fermentalab.recipes import Recipe
from fermentalab.storage import RecipeStore, StorageError


class TestControlledCancellation(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        database = Path(self.temp.name) / "fermentalab.db"

        self.store = RecipeStore(database)
        self.store.initialise()

        recipe = Recipe.from_dict({
            "schema_version": 1,
            "id": "cancellation-test",
            "name": "Cancellation Test",
            "stages": [
                {
                    "name": "Fermentation",
                    "duration_minutes": 60,
                    "temperature_c": 30.0,
                    "humidity_percent": None,
                },
            ],
        })

        self.store.save_recipe(recipe)
        self.run_id = self.store.create_run(recipe.id)

    def cancel_cli(self):
        return cancel_fermentation_run(
            self.store,
            SimpleNamespace(run_id=self.run_id),
        )

    def test_cli_cancels_created_run(self):
        self.assertEqual(self.cancel_cli(), 0)

        run = self.store.get_run(self.run_id)

        self.assertEqual(run["status"], "cancelled")
        self.assertIsNotNone(run["ended_at"])
        self.assertIsNone(run["running_since"])

    def test_cli_cancels_paused_run(self):
        self.store.transition_run(self.run_id, "start")
        self.store.transition_run(self.run_id, "pause")

        self.assertEqual(self.cancel_cli(), 0)

        run = self.store.get_run(self.run_id)

        self.assertEqual(run["status"], "cancelled")
        self.assertIsNotNone(run["ended_at"])
        self.assertIsNone(run["running_since"])

    def test_cli_rejects_running_run(self):
        self.store.transition_run(self.run_id, "start")

        before = self.store.get_run(self.run_id)

        with self.assertRaises(ValueError):
            self.cancel_cli()

        after = self.store.get_run(self.run_id)

        self.assertEqual(after["status"], "running")
        self.assertEqual(
            after["running_since"],
            before["running_since"],
        )
        self.assertIsNone(after["ended_at"])

    def test_cli_rejects_terminal_run(self):
        self.store.transition_run(self.run_id, "cancel")

        before = self.store.get_run(self.run_id)

        with self.assertRaises(ValueError):
            self.cancel_cli()

        after = self.store.get_run(self.run_id)

        self.assertEqual(after["status"], "cancelled")
        self.assertEqual(
            after["ended_at"],
            before["ended_at"],
        )

    def test_stale_cli_observation_cannot_cancel_running(self):
        original_get_run = self.store.get_run
        observed = False

        def interleaved_get_run(run_id):
            nonlocal observed

            result = original_get_run(run_id)

            if run_id == self.run_id and not observed:
                observed = True

                # CLI has observed CREATED.
                # Another process starts the run before
                # the restricted cancellation transaction.
                self.store.transition_run(
                    self.run_id,
                    "start",
                )

            return result

        with patch.object(
            self.store,
            "get_run",
            side_effect=interleaved_get_run,
        ):
            with self.assertRaisesRegex(
                StorageError,
                "caller restriction rejected transition",
            ):
                self.cancel_cli()

        self.assertTrue(observed)

        run = original_get_run(self.run_id)

        self.assertEqual(run["status"], "running")
        self.assertIsNotNone(run["running_since"])
        self.assertIsNone(run["ended_at"])

    def test_controller_owned_cancel_remains_supported(self):
        self.store.transition_run(self.run_id, "start")

        run = self.store.transition_run(
            self.run_id,
            "cancel",
        )

        self.assertEqual(run["status"], "cancelled")
        self.assertIsNotNone(run["ended_at"])
        self.assertIsNone(run["running_since"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
