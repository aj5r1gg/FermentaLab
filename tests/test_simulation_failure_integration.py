"""
FermentaLab coordinated simulation failure integration tests.

These tests verify failure handling between SimulationRunner,
ExecutionCoordinator and persistent fermentation-run storage.

Simulation only. No physical hardware is controlled.
"""

import tempfile
import unittest

from pathlib import Path
from unittest.mock import patch

from fermentalab.command_admission import (
    SimulatedCommandAdmission,
)
from fermentalab.execution_coordinator import (
    ExecutionCoordinator,
)
from fermentalab.fermentation_runtime import RuntimeState
from fermentalab.recipes import Recipe
from fermentalab.simulation_runner import SimulationRunner
from fermentalab.storage import RecipeStore
from fermentalab.thermal_model import ThermalModel


class TestSimulationFailureIntegration(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        database = Path(self.temp.name) / "fermentalab.db"

        self.store = RecipeStore(database)
        self.store.initialise()

        self.recipe = Recipe.from_dict({
            "schema_version": 1,
            "id": "simulation-failure-test",
            "name": "Simulation Failure Test",
            "stages": [
                {
                    "name": "Fermentation",
                    "duration_minutes": 60,
                    "temperature_c": 30.0,
                    "humidity_percent": None,
                },
            ],
        })

        self.store.save_recipe(self.recipe)

        self.run_id = self.store.create_run(
            self.recipe.id
        )

        self.coordinator = ExecutionCoordinator(
            store=self.store,
            run_id=self.run_id,
        )

        self.runner = SimulationRunner(
            self.recipe,
            initial_c=25.0,
            step_s=5.0,
        )

    def assert_failed_and_inhibited(self):
        run = self.store.get_run(self.run_id)

        self.assertEqual(
            run["status"],
            "failed",
        )

        self.assertIsNotNone(
            run["ended_at"],
        )

        self.assertIsNone(
            run["running_since"],
        )

        self.assertEqual(
            self.coordinator.runtime.state,
            RuntimeState.INHIBITED,
        )

        self.assertFalse(
            self.coordinator.runtime.supervisor
            ._authority.authorised
        )

    def test_cancelled_run_preserved_after_simulation_failure(self):

        def cancel_then_fail(elapsed_s):
            self.store.transition_run(
                self.run_id,
                "cancel",
            )

            raise RuntimeError(
                "Simulated failure after cancellation"
            )

        with self.assertRaisesRegex(
            RuntimeError,
            "Simulated failure after cancellation",
        ):
            self.runner.run(
                ambient_c=cancel_then_fail,
                coordinator=self.coordinator,
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

    def test_paused_run_preserved_after_simulation_failure(self):

        def pause_then_fail(elapsed_s):
            self.store.transition_run(
                self.run_id,
                "pause",
            )

            raise RuntimeError(
                "Simulated failure after pause"
            )

        with self.assertRaisesRegex(
            RuntimeError,
            "Simulated failure after pause",
        ):
            self.runner.run(
                ambient_c=pause_then_fail,
                coordinator=self.coordinator,
            )

        run = self.store.get_run(self.run_id)

        self.assertEqual(
            run["status"],
            "paused",
        )

        self.assertEqual(
            self.coordinator.runtime.state,
            RuntimeState.INHIBITED,
        )

    def test_completed_run_preserved_after_final_observer_failure(self):

        def final_observer_failure(observation):
            if observation.state == RuntimeState.COMPLETED:
                raise RuntimeError(
                    "Simulated final observer failure"
                )

        with self.assertRaisesRegex(
            RuntimeError,
            "Simulated final observer failure",
        ):
            self.runner.run(
                ambient_c=30.0,
                coordinator=self.coordinator,
                observer=final_observer_failure,
            )

        run = self.store.get_run(self.run_id)

        self.assertEqual(
            run["status"],
            "completed",
        )

        self.assertIsNotNone(
            run["completed_at"],
        )

        self.assertIsNotNone(
            run["ended_at"],
        )

        self.assertEqual(
            self.coordinator.runtime.state,
            RuntimeState.INHIBITED,
        )

    def test_cancellation_between_abort_read_and_transition(self):
        """
        Cancellation wins after abort_execution reads RUNNING
        but before its conditional failure transition.
        """
        original_transition = self.store.transition_run

        def competing_transition(run_id, action, **kwargs):
            if (
                action == "fail"
                and kwargs.get("allowed_from") == ("running",)
            ):
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

        def failing_ambient(elapsed_s):
            raise RuntimeError(
                "Original simulation failure"
            )

        with patch.object(
            self.store,
            "transition_run",
            side_effect=competing_transition,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "Original simulation failure",
            ):
                self.runner.run(
                    ambient_c=failing_ambient,
                    coordinator=self.coordinator,
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

    def test_genuine_failure_persistence_error_remains_visible(self):
        """
        A failed persistence operation must not be mistaken
        for a legitimate competing lifecycle transition.
        """
        from fermentalab.storage import StorageError

        original_transition = self.store.transition_run

        def failing_transition(run_id, action, **kwargs):
            if (
                action == "fail"
                and kwargs.get("allowed_from") == ("running",)
            ):
                raise StorageError(
                    "Simulated failure persistence error"
                )

            return original_transition(
                run_id,
                action,
                **kwargs,
            )

        def failing_ambient(elapsed_s):
            raise RuntimeError(
                "Original simulation failure"
            )

        with patch.object(
            self.store,
            "transition_run",
            side_effect=failing_transition,
        ):
            with self.assertRaisesRegex(
                StorageError,
                "Simulated failure persistence error",
            ):
                self.runner.run(
                    ambient_c=failing_ambient,
                    coordinator=self.coordinator,
                )

        run = self.store.get_run(self.run_id)

        # Persistence failed, so the database still
        # records RUNNING. This must not be concealed.
        self.assertEqual(
            run["status"],
            "running",
        )

        # The in-memory runtime must nevertheless
        # have been inhibited.
        self.assertEqual(
            self.coordinator.runtime.state,
            RuntimeState.INHIBITED,
        )

    def test_ambient_callback_failure(self):

        def failing_ambient(elapsed_s):
            raise RuntimeError(
                "Simulated ambient callback failure"
            )

        with self.assertRaisesRegex(
            RuntimeError,
            "Simulated ambient callback failure",
        ):
            self.runner.run(
                ambient_c=failing_ambient,
                coordinator=self.coordinator,
            )

        self.assert_failed_and_inhibited()

    def test_observer_failure(self):

        def failing_observer(observation):
            raise RuntimeError(
                "Simulated observer failure"
            )

        with self.assertRaisesRegex(
            RuntimeError,
            "Simulated observer failure",
        ):
            self.runner.run(
                ambient_c=35.0,
                coordinator=self.coordinator,
                observer=failing_observer,
            )

        self.assert_failed_and_inhibited()

    def test_thermal_model_failure(self):

        with patch.object(
            ThermalModel,
            "step",
            side_effect=RuntimeError(
                "Simulated thermal-model failure"
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "Simulated thermal-model failure",
            ):
                self.runner.run(
                    ambient_c=35.0,
                    coordinator=self.coordinator,
                )

        self.assert_failed_and_inhibited()


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestPersistentCommandAdmissionIntegration(
    TestSimulationFailureIntegration
):

    def make_authority(self, *, enabled):
        authority = SimulatedCommandAdmission()

        identity = authority.acquire(
            execution_session_id=self.run_id
        )

        if enabled:
            authority.enable(identity)

        return authority, identity

    def test_persistent_inhibited_authority_prevents_heating(self):
        authority, identity = self.make_authority(
            enabled=False
        )

        result = self.runner.run(
            ambient_c=20.0,
            coordinator=self.coordinator,
            command_admission=authority,
            command_identity=identity,
        )

        self.assertEqual(
            result.state,
            RuntimeState.COMPLETED,
        )
        self.assertEqual(result.heating_seconds, 0.0)
        self.assertFalse(authority.enabled)

    def test_persistent_enabled_authority_and_completion(self):
        authority, identity = self.make_authority(
            enabled=True
        )

        result = self.runner.run(
            ambient_c=20.0,
            coordinator=self.coordinator,
            command_admission=authority,
            command_identity=identity,
        )

        self.assertEqual(
            result.state,
            RuntimeState.COMPLETED,
        )
        self.assertGreater(result.heating_seconds, 0.0)
        self.assertFalse(authority.enabled)

        rejected = authority.admit(
            identity=identity,
            heating=True,
            cooling=False,
        )

        self.assertFalse(rejected.accepted)

    def test_persistent_failure_revokes_authority(self):
        authority, identity = self.make_authority(
            enabled=True
        )

        def failing_ambient(elapsed_s):
            if elapsed_s >= 5.0:
                raise RuntimeError(
                    "Injected persistent authority failure"
                )
            return 20.0

        with self.assertRaisesRegex(
            RuntimeError,
            "Injected persistent authority failure",
        ):
            self.runner.run(
                ambient_c=failing_ambient,
                coordinator=self.coordinator,
                command_admission=authority,
                command_identity=identity,
            )

        self.assertFalse(authority.enabled)

        rejected = authority.admit(
            identity=identity,
            heating=True,
            cooling=False,
        )

        self.assertFalse(rejected.accepted)

        self.assert_failed_and_inhibited()


class TestPersistentExecutionSessionFencing(
    TestSimulationFailureIntegration
):

    def test_unrelated_execution_session_rejected(self):
        authority = SimulatedCommandAdmission()

        identity = authority.acquire(
            execution_session_id="unrelated-execution-session"
        )
        authority.enable(identity)

        with self.assertRaises(
            (ValueError, RuntimeError),
            msg="Unrelated execution identity was accepted",
        ):
            self.runner.run(
                ambient_c=20.0,
                coordinator=self.coordinator,
                command_admission=authority,
                command_identity=identity,
            )

        self.assertFalse(
            authority.enabled,
            "Rejected execution left authority enabled",
        )

        rejected = authority.admit(
            identity=identity,
            heating=True,
            cooling=False,
        )

        self.assertFalse(rejected.accepted)


class TestPersistentActiveIdentityFencing(
    TestSimulationFailureIntegration
):

    def test_stale_identity_rejected_before_execution(self):
        authority = SimulatedCommandAdmission()

        old_identity = authority.acquire(
            execution_session_id=self.run_id
        )

        authority.enable(old_identity)

        # Advance the inhibition generation, invalidating
        # the previously issued identity.
        new_identity = authority.inhibit(old_identity)
        authority.enable(new_identity)

        with self.assertRaises(
            (ValueError, RuntimeError),
            msg="Stale identity was accepted for execution",
        ):
            self.runner.run(
                ambient_c=20.0,
                coordinator=self.coordinator,
                command_admission=authority,
                command_identity=old_identity,
            )

        self.assertFalse(
            authority.enabled,
            "Rejected startup left authority enabled",
        )

        rejected = authority.admit(
            identity=new_identity,
            heating=True,
            cooling=False,
        )

        self.assertFalse(
            rejected.accepted,
            "Rejected startup retained active ON authority",
        )

        run = self.store.get_run(self.run_id)

        self.assertEqual(
            run["status"],
            "created",
            "Rejected startup changed persistent run state",
        )


class TestPersistentStartupAuthorityCleanup(
    TestSimulationFailureIntegration
):

    def test_coordinator_start_failure_revokes_authority(self):
        authority = SimulatedCommandAdmission()

        identity = authority.acquire(
            execution_session_id=self.run_id
        )
        authority.enable(identity)

        with patch.object(
            self.coordinator,
            "start",
            side_effect=RuntimeError(
                "Injected coordinator startup failure"
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "Injected coordinator startup failure",
            ):
                self.runner.run(
                    ambient_c=20.0,
                    coordinator=self.coordinator,
                    command_admission=authority,
                    command_identity=identity,
                )

        self.assertFalse(
            authority.enabled,
            "Startup failure left command authority enabled",
        )

        rejected = authority.admit(
            identity=identity,
            heating=True,
            cooling=False,
        )

        self.assertFalse(
            rejected.accepted,
            "Startup failure retained ON authority",
        )
