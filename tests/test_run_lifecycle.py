"""FermentaLab fermentation-run lifecycle acceptance tests."""

import tempfile
import unittest
from pathlib import Path

from fermentalab.recipes import Recipe
from fermentalab.storage import RecipeStore, StorageError


def example_recipe():
    return Recipe.from_dict({
        "schema_version": 1,
        "id": "lifecycle-test",
        "name": "Lifecycle Test",
        "stages": [
            {
                "name": "Incubation",
                "duration_minutes": 120,
                "temperature_c": 35.0,
                "humidity_percent": None,
            }
        ],
    })


class TestRunLifecycle(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        database = Path(self.temp.name) / "fermentalab.db"

        self.store = RecipeStore(database)
        self.store.initialise()

        self.recipe = example_recipe()
        self.store.save_recipe(self.recipe)

        self.run_id = self.store.create_run(self.recipe.id)

    def transition(self, action):
        return self.store.transition_run(
            self.run_id,
            action,
        )

    def test_start_created_run(self):
        self.transition("start")

        run = self.store.get_run(self.run_id)

        self.assertEqual(run["status"], "running")
        self.assertIsNotNone(run["started_at"])
        self.assertIsNotNone(run["running_since"])

    def test_pause_running_run(self):
        self.transition("start")
        self.transition("pause")

        run = self.store.get_run(self.run_id)

        self.assertEqual(run["status"], "paused")
        self.assertIsNone(run["running_since"])
        self.assertIsNotNone(run["paused_at"])

    def test_resume_paused_run(self):
        self.transition("start")
        self.transition("pause")
        self.transition("resume")

        run = self.store.get_run(self.run_id)

        self.assertEqual(run["status"], "running")
        self.assertIsNotNone(run["running_since"])

    def test_complete_running_run(self):
        self.transition("start")
        self.transition("complete")

        run = self.store.get_run(self.run_id)

        self.assertEqual(run["status"], "completed")
        self.assertIsNotNone(run["completed_at"])
        self.assertIsNotNone(run["ended_at"])
        self.assertIsNone(run["running_since"])

    def test_cancel_created_run(self):
        self.transition("cancel")

        run = self.store.get_run(self.run_id)

        self.assertEqual(run["status"], "cancelled")
        self.assertIsNotNone(run["ended_at"])

    def test_cancel_paused_run(self):
        self.transition("start")
        self.transition("pause")
        self.transition("cancel")

        self.assertEqual(
            self.store.get_run(self.run_id)["status"],
            "cancelled",
        )

    def test_fail_created_run(self):
        self.transition("fail")

        run = self.store.get_run(self.run_id)

        self.assertEqual(run["status"], "failed")
        self.assertIsNotNone(run["ended_at"])

    def test_reject_pause_before_start(self):
        with self.assertRaises(StorageError):
            self.transition("pause")

    def test_reject_resume_before_start(self):
        with self.assertRaises(StorageError):
            self.transition("resume")

    def test_reject_complete_before_start(self):
        with self.assertRaises(StorageError):
            self.transition("complete")

    def test_reject_double_start(self):
        self.transition("start")

        with self.assertRaises(StorageError):
            self.transition("start")

    def test_terminal_state_is_immutable(self):
        self.transition("cancel")

        for action in (
            "start",
            "pause",
            "resume",
            "complete",
            "cancel",
            "fail",
        ):
            with self.subTest(action=action):
                with self.assertRaises(StorageError):
                    self.transition(action)

    def test_unknown_action_rejected(self):
        with self.assertRaises(StorageError):
            self.transition("explode")

    def test_missing_run_rejected(self):
        with self.assertRaises(StorageError):
            self.store.transition_run(
                "nonexistent-run",
                "start",
            )

    def test_recipe_snapshot_preserved(self):
        self.transition("start")
        self.transition("pause")
        self.transition("resume")

        run = self.store.get_run(self.run_id)

        self.assertEqual(run["recipe"], self.recipe)


if __name__ == "__main__":
    unittest.main(verbosity=2)
