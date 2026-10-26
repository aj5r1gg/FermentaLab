"""
FermentaLab persistent cancellation integration tests.

Simulation only. No physical actuator control.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fermentalab.execution_coordinator import (
    ExecutionCoordinator,
)
from fermentalab.fermentation_runtime import RuntimeState
from fermentalab.recipes import Recipe
from fermentalab.storage import RecipeStore


class TestExecutionCancellationIntegration(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        database = Path(self.temp.name) / "fermentalab.db"

        self.store = RecipeStore(database)
        self.store.initialise()

        recipe = Recipe.from_dict({
            "schema_version": 1,
            "id": "execution-cancellation-test",
            "name": "Execution Cancellation Test",
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

        self.coordinator = ExecutionCoordinator(
            store=self.store,
            run_id=self.run_id,
        )

        self.coordinator.start(now_s=0.0)

    def test_persistent_cancellation_inhibits_execution(self):
        self.store.transition_run(
            self.run_id,
            "cancel",
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "Persistent run is not running: cancelled",
        ):
            self.coordinator.advance(
                chamber_c=25.0,
                measured_at_s=5.0,
                now_s=5.0,
            )

        self.assertEqual(
            self.coordinator.runtime.state,
            RuntimeState.INHIBITED,
        )

        self.assertEqual(
            self.store.get_run(self.run_id)["status"],
            "cancelled",
        )

    def test_persistent_pause_inhibits_execution(self):
        self.store.transition_run(
            self.run_id,
            "pause",
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "Persistent run is not running: paused",
        ):
            self.coordinator.advance(
                chamber_c=25.0,
                measured_at_s=5.0,
                now_s=5.0,
            )

        self.assertEqual(
            self.coordinator.runtime.state,
            RuntimeState.INHIBITED,
        )

        self.assertEqual(
            self.store.get_run(self.run_id)["status"],
            "paused",
        )

    def test_cancellation_during_evaluation_inhibits_runtime(self):
        original_evaluate = self.coordinator.runtime.evaluate

        def cancel_during_evaluation(**kwargs):
            # The coordinator has already checked RUNNING.
            # A competing controller now cancels the run.
            self.store.transition_run(
                self.run_id,
                "cancel",
            )

            return original_evaluate(**kwargs)

        with patch.object(
            self.coordinator.runtime,
            "evaluate",
            side_effect=cancel_during_evaluation,
        ):
            with self.assertRaises(RuntimeError):
                self.coordinator.advance(
                    chamber_c=25.0,
                    measured_at_s=5.0,
                    now_s=5.0,
                )

        self.assertEqual(
            self.coordinator.runtime.state,
            RuntimeState.INHIBITED,
        )

        run = self.store.get_run(self.run_id)

        self.assertEqual(
            run["status"],
            "cancelled",
        )

        self.assertIsNone(
            run["completed_at"],
        )

    def test_cancellation_during_advance_failure_cleanup(self):
        """
        Cancellation wins between the advance failure
        handler's state read and its failure transition.

        The original execution exception must survive.
        """
        original_transition = self.store.transition_run

        def competing_transition(run_id, action, **kwargs):
            if action == "fail":
                original_transition(
                    run_id,
                    "cancel",
                    allowed_from=("running",),
                )

            return original_transition(
                run_id,
                action,
                **kwargs,
            )

        with patch.object(
            self.coordinator.runtime,
            "evaluate",
            side_effect=RuntimeError(
                "Original execution failure"
            ),
        ):
            with patch.object(
                self.store,
                "transition_run",
                side_effect=competing_transition,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "Original execution failure",
                ):
                    self.coordinator.advance(
                        chamber_c=25.0,
                        measured_at_s=5.0,
                        now_s=5.0,
                    )

        run = self.store.get_run(self.run_id)

        self.assertEqual(
            run["status"],
            "cancelled",
        )

        self.assertEqual(
            self.coordinator.runtime.state,
            RuntimeState.INHIBITED,
        )

    def test_cancelled_run_cannot_be_completed(self):
        self.store.transition_run(
            self.run_id,
            "cancel",
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "Persistent run is not running: cancelled",
        ):
            self.coordinator.advance(
                chamber_c=25.0,
                measured_at_s=3600.0,
                now_s=3600.0,
            )

        run = self.store.get_run(self.run_id)

        self.assertEqual(
            run["status"],
            "cancelled",
        )

        self.assertIsNone(
            run["completed_at"],
        )

        self.assertIsNotNone(
            run["ended_at"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
