"""
FermentaLab execution integration acceptance tests.

These tests establish contracts for future coordination
between persistent fermentation runs and the simulation
runtime.

No physical hardware is controlled.
"""

import tempfile
import unittest
from unittest.mock import patch

from pathlib import Path

from fermentalab.recipes import Recipe
from fermentalab.storage import RecipeStore


def make_recipe(temperature_c):
    return Recipe.from_dict({
        "schema_version": 1,
        "id": "execution-integration-test",
        "name": "Execution Integration Test",
        "stages": [
            {
                "name": "Fermentation",
                "duration_minutes": 60,
                "temperature_c": temperature_c,
                "humidity_percent": None,
            },
        ],
    })


class TestExecutionIntegration(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        database = Path(self.temp.name) / "fermentalab.db"

        self.store = RecipeStore(database)
        self.store.initialise()

    def test_execution_starts_from_persisted_snapshot(self):
        from fermentalab.execution_coordinator import (
            ExecutionCoordinator,
        )

        original = make_recipe(30.0)
        self.store.save_recipe(original)

        run_id = self.store.create_run(original.id)

        # Editing the recipe must not alter the execution target.
        self.store.save_recipe(make_recipe(35.0))

        coordinator = ExecutionCoordinator(
            store=self.store,
            run_id=run_id,
        )

        self.assertEqual(
            coordinator.runtime.recipe,
            original,
        )

        self.assertEqual(
            self.store.get_run(run_id)["status"],
            "created",
        )

        decision = coordinator.start(now_s=100.0)

        self.assertEqual(decision.state.value, "running")
        self.assertFalse(decision.heating_permitted)
        self.assertFalse(decision.cooling_permitted)

        self.assertEqual(
            self.store.get_run(run_id)["status"],
            "running",
        )

        self.assertEqual(
            coordinator.runtime.recipe.stages[0].temperature_c,
            30.0,
        )

    def test_persistence_failure_inhibits_runtime(self):
        from fermentalab.execution_coordinator import (
            ExecutionCoordinator,
        )
        from fermentalab.fermentation_runtime import (
            RuntimeState,
        )
        from fermentalab.storage import StorageError

        original = make_recipe(30.0)

        self.store.save_recipe(original)

        run_id = self.store.create_run(original.id)

        coordinator = ExecutionCoordinator(
            store=self.store,
            run_id=run_id,
        )

        with patch.object(
            self.store,
            "transition_run",
            side_effect=StorageError(
                "Simulated SQLite transition failure"
            ),
        ):
            with self.assertRaisesRegex(
                StorageError,
                "Simulated SQLite transition failure",
            ):
                coordinator.start(now_s=100.0)

        self.assertEqual(
            coordinator.runtime.state,
            RuntimeState.INHIBITED,
        )

        self.assertEqual(
            coordinator.runtime.supervisor.state.value,
            "inhibited",
        )

        self.assertFalse(
            coordinator.runtime.supervisor._authority.authorised
        )

        self.assertEqual(
            self.store.get_run(run_id)["status"],
            "created",
        )

    def test_same_coordinator_cannot_start_twice(self):
        from fermentalab.execution_coordinator import (
            ExecutionCoordinator,
        )
        from fermentalab.fermentation_runtime import (
            RuntimeState,
        )

        self.store.save_recipe(make_recipe(30.0))

        run_id = self.store.create_run(
            "execution-integration-test"
        )

        coordinator = ExecutionCoordinator(
            store=self.store,
            run_id=run_id,
        )

        first = coordinator.start(now_s=100.0)

        self.assertEqual(
            first.state,
            RuntimeState.RUNNING,
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "already started",
        ):
            coordinator.start(now_s=101.0)

        self.assertEqual(
            coordinator.runtime.state,
            RuntimeState.RUNNING,
        )

        self.assertEqual(
            self.store.get_run(run_id)["status"],
            "running",
        )

    def test_competing_coordinator_cannot_start_same_run(self):
        from fermentalab.execution_coordinator import (
            ExecutionCoordinator,
        )
        from fermentalab.fermentation_runtime import (
            RuntimeState,
        )
        from fermentalab.storage import StorageError

        self.store.save_recipe(make_recipe(30.0))

        run_id = self.store.create_run(
            "execution-integration-test"
        )

        # Both coordinators load the same CREATED record.
        first = ExecutionCoordinator(
            store=self.store,
            run_id=run_id,
        )

        second = ExecutionCoordinator(
            store=self.store,
            run_id=run_id,
        )

        first.start(now_s=100.0)

        with self.assertRaisesRegex(
            StorageError,
            "not eligible to start",
        ):
            second.start(now_s=101.0)

        self.assertEqual(
            first.runtime.state,
            RuntimeState.RUNNING,
        )

        self.assertEqual(
            second.runtime.state,
            RuntimeState.INHIBITED,
        )

        self.assertFalse(
            second.runtime.supervisor._authority.authorised
        )

        self.assertEqual(
            self.store.get_run(run_id)["status"],
            "running",
        )

    def test_interleaved_starts_do_not_create_two_active_runtimes(self):
        from fermentalab.execution_coordinator import (
            ExecutionCoordinator,
        )
        from fermentalab.fermentation_runtime import (
            RuntimeState,
        )
        from fermentalab.storage import StorageError

        self.store.save_recipe(make_recipe(30.0))

        run_id = self.store.create_run(
            "execution-integration-test"
        )

        first = ExecutionCoordinator(
            store=self.store,
            run_id=run_id,
        )

        second = ExecutionCoordinator(
            store=self.store,
            run_id=run_id,
        )

        original_transition = self.store.transition_run

        second_started = False

        def interleaved_transition(target_run_id, action):
            nonlocal second_started

            if (
                target_run_id == run_id
                and action == "start"
                and not second_started
            ):
                second_started = True

                # Coordinator A has activated its runtime
                # but has not persisted RUNNING.
                #
                # Coordinator B attempts to start during
                # that execution window.
                second.start(now_s=101.0)

            return original_transition(
                target_run_id,
                action,
            )

        with patch.object(
            self.store,
            "transition_run",
            side_effect=interleaved_transition,
        ):
            with self.assertRaises(StorageError):
                first.start(now_s=100.0)

        self.assertTrue(second_started)

        self.assertEqual(
            self.store.get_run(run_id)["status"],
            "running",
        )

        # The losing coordinator must be inhibited.
        self.assertEqual(
            first.runtime.state,
            RuntimeState.INHIBITED,
        )

        # The successful coordinator is the sole owner.
        self.assertEqual(
            second.runtime.state,
            RuntimeState.RUNNING,
        )

        self.assertFalse(
            first.runtime.supervisor._authority.authorised
        )

    def test_no_actuator_permission_before_persistent_start(self):
        from fermentalab.execution_coordinator import (
            ExecutionCoordinator,
        )
        from fermentalab.fermentation_runtime import (
            RuntimeState,
        )

        self.store.save_recipe(make_recipe(30.0))

        run_id = self.store.create_run(
            "execution-integration-test"
        )

        coordinator = ExecutionCoordinator(
            store=self.store,
            run_id=run_id,
        )

        observed = []

        original_transition = self.store.transition_run

        def inspect_before_commit(target_run_id, action):
            self.assertEqual(target_run_id, run_id)
            self.assertEqual(action, "start")

            # The database has not yet recorded RUNNING.
            self.assertEqual(
                self.store.get_run(run_id)["status"],
                "created",
            )

            # Attempt a valid temperature evaluation while
            # the persistent start transition is pending.
            # Before persistence completes, the runtime
            # must reject temperature evaluation entirely.
            with self.assertRaisesRegex(
                RuntimeError,
                "runtime is not running",
            ):
                coordinator.runtime.evaluate(
                    chamber_c=25.0,
                    measured_at_s=100.0,
                    now_s=100.0,
                )

            observed.append("evaluation rejected")

            return original_transition(
                target_run_id,
                action,
            )

        with patch.object(
            self.store,
            "transition_run",
            side_effect=inspect_before_commit,
        ):
            coordinator.start(now_s=100.0)

        self.assertEqual(len(observed), 1)

        # An uncommitted execution must not be able to
        # expose actuator permission.
        self.assertEqual(
            observed[0],
            "evaluation rejected",
        )

        self.assertEqual(
            self.store.get_run(run_id)["status"],
            "running",
        )

        self.assertEqual(
            coordinator.runtime.state,
            RuntimeState.RUNNING,
        )

    def test_cancellation_during_failed_activation_is_preserved(self):
        """
        Cancellation during activation must survive
        an independent runtime activation failure.
        """
        from fermentalab.execution_coordinator import ExecutionCoordinator
        from fermentalab.fermentation_runtime import RuntimeState

        self.store.save_recipe(make_recipe(30.0))
        run_id = self.store.create_run("execution-integration-test")

        coordinator = ExecutionCoordinator(
            store=self.store,
            run_id=run_id,
        )

        def failing_activation(*, now_s):
            self.store.transition_run(
                run_id,
                "cancel",
                allowed_from=("running",),
            )
            raise RuntimeError("Activation failed after cancellation")

        with patch.object(
            coordinator.runtime,
            "start",
            side_effect=failing_activation,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "Activation failed after cancellation",
            ):
                coordinator.start(now_s=100.0)

        self.assertEqual(
            self.store.get_run(run_id)["status"],
            "cancelled",
        )
        self.assertEqual(
            coordinator.runtime.state,
            RuntimeState.INHIBITED,
        )

    def test_cancellation_during_successful_activation_is_rejected(self):
        """
        Successful runtime activation must not override
        cancellation of the persistent run.
        """
        from fermentalab.execution_coordinator import ExecutionCoordinator
        from fermentalab.fermentation_runtime import RuntimeState

        self.store.save_recipe(make_recipe(30.0))
        run_id = self.store.create_run("execution-integration-test")

        coordinator = ExecutionCoordinator(
            store=self.store,
            run_id=run_id,
        )

        original_start = coordinator.runtime.start

        def cancelling_activation(*, now_s):
            decision = original_start(now_s=now_s)

            self.store.transition_run(
                run_id,
                "cancel",
                allowed_from=("running",),
            )

            return decision

        with patch.object(
            coordinator.runtime,
            "start",
            side_effect=cancelling_activation,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "Persistent run changed during activation",
            ):
                coordinator.start(now_s=100.0)

        self.assertEqual(
            self.store.get_run(run_id)["status"],
            "cancelled",
        )
        self.assertEqual(
            coordinator.runtime.state,
            RuntimeState.INHIBITED,
        )
        self.assertFalse(coordinator._started)

    def test_runtime_activation_failure_marks_run_failed(self):
        from fermentalab.execution_coordinator import (
            ExecutionCoordinator,
        )
        from fermentalab.fermentation_runtime import (
            RuntimeState,
        )

        self.store.save_recipe(make_recipe(30.0))

        run_id = self.store.create_run(
            "execution-integration-test"
        )

        coordinator = ExecutionCoordinator(
            store=self.store,
            run_id=run_id,
        )

        with patch.object(
            coordinator.runtime,
            "start",
            side_effect=RuntimeError(
                "Simulated runtime activation failure"
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "Simulated runtime activation failure",
            ):
                coordinator.start(now_s=100.0)

        self.assertEqual(
            coordinator.runtime.state,
            RuntimeState.INHIBITED,
        )

        self.assertFalse(
            coordinator.runtime.supervisor._authority.authorised
        )

        self.assertEqual(
            self.store.get_run(run_id)["status"],
            "failed",
        )

    def test_activation_and_failure_recording_both_fail(self):
        from fermentalab.execution_coordinator import (
            ExecutionCoordinator,
        )
        from fermentalab.fermentation_runtime import (
            RuntimeState,
        )
        from fermentalab.storage import StorageError

        self.store.save_recipe(make_recipe(30.0))

        run_id = self.store.create_run(
            "execution-integration-test"
        )

        coordinator = ExecutionCoordinator(
            store=self.store,
            run_id=run_id,
        )

        original_transition = self.store.transition_run

        def transition_with_failure(
            target_run_id,
            action,
            **kwargs,
        ):
            if action == "fail":
                raise StorageError(
                    "Simulated failure-recording error"
                )

            return original_transition(
                target_run_id,
                action,
                **kwargs,
            )

        with patch.object(
            coordinator.runtime,
            "start",
            side_effect=RuntimeError(
                "Simulated runtime activation failure"
            ),
        ):
            with patch.object(
                self.store,
                "transition_run",
                side_effect=transition_with_failure,
            ):
                with self.assertRaisesRegex(
                    StorageError,
                    "Simulated failure-recording error",
                ):
                    coordinator.start(now_s=100.0)

        self.assertEqual(
            coordinator.runtime.state,
            RuntimeState.INHIBITED,
        )

        self.assertEqual(
            coordinator.runtime.supervisor.state.value,
            "inhibited",
        )

        self.assertFalse(
            coordinator.runtime.supervisor._authority.authorised
        )

        # Persistence succeeded for START but failed
        # when attempting to record the activation failure.
        self.assertEqual(
            self.store.get_run(run_id)["status"],
            "running",
        )

    def test_double_failure_record_recovers_without_runtime_activation(self):
        from fermentalab.execution_coordinator import (
            ExecutionCoordinator,
        )
        from fermentalab.fermentation_runtime import (
            RuntimeState,
        )
        from fermentalab.storage import StorageError

        self.store.save_recipe(make_recipe(30.0))

        run_id = self.store.create_run(
            "execution-integration-test"
        )

        coordinator = ExecutionCoordinator(
            store=self.store,
            run_id=run_id,
        )

        original_transition = self.store.transition_run

        def transition_with_failure(
            target_run_id,
            action,
            **kwargs,
        ):
            if action == "fail":
                raise StorageError(
                    "Simulated failure-recording error"
                )

            return original_transition(
                target_run_id,
                action,
                **kwargs,
            )

        with patch.object(
            coordinator.runtime,
            "start",
            side_effect=RuntimeError(
                "Simulated runtime activation failure"
            ),
        ):
            with patch.object(
                self.store,
                "transition_run",
                side_effect=transition_with_failure,
            ):
                with self.assertRaises(StorageError):
                    coordinator.start(now_s=100.0)

        before = self.store.get_run(run_id)

        self.assertEqual(
            before["status"],
            "running",
        )

        self.assertEqual(
            coordinator.runtime.state,
            RuntimeState.INHIBITED,
        )

        self.assertFalse(
            coordinator.runtime.supervisor._authority.authorised
        )

        # Simulate controller startup recovery.
        self.store.recover_interrupted_runs()

        recovered = self.store.get_run(run_id)

        self.assertEqual(
            recovered["status"],
            "paused",
        )

        self.assertIsNone(
            recovered["running_since"],
        )

        self.assertIsNotNone(
            recovered["paused_at"],
        )

        self.assertIn(
            "unobserved elapsed time excluded",
            recovered["failure_reason"],
        )

        # No runtime activation is permitted by recovery.
        self.assertEqual(
            coordinator.runtime.state,
            RuntimeState.INHIBITED,
        )

        self.assertFalse(
            coordinator.runtime.supervisor._authority.authorised
        )

        elapsed_before_repeat = recovered[
            "elapsed_microseconds"
        ]

        self.store.recover_interrupted_runs()

        repeated = self.store.get_run(run_id)

        self.assertEqual(
            repeated["status"],
            "paused",
        )

        self.assertEqual(
            repeated["elapsed_microseconds"],
            elapsed_before_repeat,
        )

        self.assertEqual(
            repeated["paused_at"],
            recovered["paused_at"],
        )

    def test_run_uses_original_recipe_snapshot(self):
        original = make_recipe(30.0)

        self.store.save_recipe(original)

        run_id = self.store.create_run(original.id)

        updated = make_recipe(35.0)

        self.store.save_recipe(updated)

        stored_run = self.store.get_run(run_id)

        self.assertEqual(
            stored_run["recipe"],
            original,
        )

        self.assertEqual(
            stored_run["recipe"].stages[0].temperature_c,
            30.0,
        )

        self.assertEqual(
            self.store.get_recipe(original.id)
            .stages[0].temperature_c,
            35.0,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
