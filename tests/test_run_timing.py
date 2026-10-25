"""Adversarial tests for fermentation-run timing."""

import tempfile
import unittest

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fermentalab.recipes import Recipe
from fermentalab.storage import RecipeStore, StorageError


BASE = datetime(
    2026, 10, 25, 12, 0, 0,
    tzinfo=timezone.utc,
)


def recipe():
    return Recipe.from_dict({
        "schema_version": 1,
        "id": "timing-test",
        "name": "Timing Test",
        "stages": [
            {
                "name": "Incubation",
                "duration_minutes": 120,
                "temperature_c": 35.0,
                "humidity_percent": None,
            }
        ],
    })


class TestRunTiming(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        database = Path(self.temp.name) / "fermentalab.db"

        self.store = RecipeStore(database)
        self.store.initialise()

        self.store.save_recipe(recipe())
        self.run_id = self.store.create_run("timing-test")

    def at(self, seconds, action):
        timestamp = (
            BASE + timedelta(seconds=seconds)
        ).isoformat()

        with patch(
            "fermentalab.storage.utc_now",
            return_value=timestamp,
        ):
            return self.store.transition_run(
                self.run_id,
                action,
            )

    def test_elapsed_time_accumulates(self):
        self.at(0, "start")
        self.at(60, "pause")
        self.at(120, "resume")
        self.at(180, "pause")

        run = self.store.get_run(self.run_id)

        self.assertEqual(run["elapsed_seconds"], 120)

    def test_paused_time_excluded(self):
        self.at(0, "start")
        self.at(30, "pause")
        self.at(3600, "resume")
        self.at(3630, "pause")

        run = self.store.get_run(self.run_id)

        self.assertEqual(run["elapsed_seconds"], 60)

    def test_subsecond_intervals_preserved(self):
        self.at(0, "start")
        self.at(0.6, "pause")
        self.at(10, "resume")
        self.at(10.6, "pause")

        run = self.store.get_run(self.run_id)

        self.assertGreaterEqual(
            run["elapsed_seconds"],
            1,
            "Repeated subsecond intervals were discarded",
        )

    def test_backward_clock_rejected_atomically(self):
        self.at(100, "start")

        with self.assertRaises(StorageError):
            self.at(90, "pause")

        run = self.store.get_run(self.run_id)

        self.assertEqual(run["status"], "running")
        self.assertEqual(run["elapsed_seconds"], 0)

    def test_recovery_does_not_assume_downtime(self):
        self.at(0, "start")

        # A restarted controller must not silently
        # count unobserved downtime as fermentation.
        recovered = self.store.recover_interrupted_runs()

        self.assertEqual(recovered, 1)

        run = self.store.get_run(self.run_id)

        self.assertEqual(run["status"], "paused")
        self.assertIsNone(run["running_since"])
        self.assertEqual(run["elapsed_seconds"], 0)

    def test_recovery_is_idempotent(self):
        self.at(0, "start")

        self.assertEqual(
            self.store.recover_interrupted_runs(),
            1,
        )

        self.assertEqual(
            self.store.recover_interrupted_runs(),
            0,
        )

    def test_recovery_preserves_created_runs(self):
        recovered = self.store.recover_interrupted_runs()

        self.assertEqual(recovered, 0)

        self.assertEqual(
            self.store.get_run(self.run_id)["status"],
            "created",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
