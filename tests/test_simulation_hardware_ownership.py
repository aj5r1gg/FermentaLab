"""End-to-end simulated hardware ownership integration."""

import tempfile
import unittest
from pathlib import Path

from fermentalab.command_admission import (
    SimulatedCommandAdmission,
)
from fermentalab.fermentation_runtime import RuntimeState
from fermentalab.hardware_owner import HardwareOwner
from fermentalab.recipes import Recipe
from fermentalab.simulation_runner import SimulationRunner


class SimulationHardwareOwnershipTests(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

        self.hardware_owner = HardwareOwner(
            Path(self.directory.name) / "controller.lock"
        )

        self.admission = SimulatedCommandAdmission(
            hardware_owner=self.hardware_owner
        )

        self.identity = self.admission.acquire(
            execution_session_id="simulation-hardware-test"
        )

        self.recipe = Recipe.from_dict({
            "schema_version": 1,
            "id": "hardware-ownership-test",
            "name": "Hardware Ownership Test",
            "stages": [
                {
                    "name": "Incubation",
                    "duration_minutes": 1,
                    "temperature_c": 35.0,
                    "humidity_percent": None,
                },
            ],
        })

        self.runner = SimulationRunner(
            self.recipe,
            initial_c=20.0,
            step_s=5.0,
        )

    def run_simulation(self, **kwargs):
        return self.runner.run(
            ambient_c=20.0,
            command_admission=self.admission,
            command_identity=self.identity,
            **kwargs,
        )

    def test_valid_ownership_permits_simulated_heating(self):
        with self.hardware_owner:
            self.admission.enable(self.identity)

            result = self.run_simulation()

            self.assertEqual(
                result.state,
                RuntimeState.COMPLETED,
            )
            self.assertGreater(result.heating_seconds, 0.0)
            self.assertFalse(self.admission.enabled)

            # The runner revokes command admission but does
            # not release externally managed hardware ownership.
            self.assertTrue(self.hardware_owner.valid())

        self.assertFalse(self.hardware_owner.acquired)

    def test_missing_ownership_prevents_simulated_heating(self):
        result = self.run_simulation()

        self.assertEqual(
            result.state,
            RuntimeState.COMPLETED,
        )
        self.assertEqual(result.heating_seconds, 0.0)
        self.assertEqual(result.cooling_seconds, 0.0)
        self.assertFalse(self.admission.enabled)

    def test_ownership_loss_prevents_subsequent_heating(self):
        self.hardware_owner.acquire()
        self.addCleanup(self.hardware_owner.release)

        self.admission.enable(self.identity)

        observations = []

        def observer(observation):
            observations.append(observation)

            if observation.elapsed_s >= 5.0:
                self.hardware_owner.release()

        result = self.run_simulation(
            observer=observer,
            report_every_s=5.0,
        )

        self.assertEqual(
            result.state,
            RuntimeState.COMPLETED,
        )

        self.assertGreater(result.heating_seconds, 0.0)
        self.assertLess(result.heating_seconds, 60.0)
        self.assertFalse(self.admission.enabled)
        self.assertFalse(self.hardware_owner.acquired)

        self.assertTrue(
            any(
                not observation.heating_permitted
                for observation in observations
                if observation.elapsed_s >= 10.0
            )
        )

    def test_exception_revokes_admission_without_releasing_lock(self):
        with self.hardware_owner:
            self.admission.enable(self.identity)

            def failing_ambient(elapsed_s):
                if elapsed_s >= 5.0:
                    raise RuntimeError(
                        "Injected simulation failure"
                    )
                return 20.0

            with self.assertRaisesRegex(
                RuntimeError,
                "Injected simulation failure",
            ):
                self.runner.run(
                    ambient_c=failing_ambient,
                    command_admission=self.admission,
                    command_identity=self.identity,
                )

            self.assertFalse(self.admission.enabled)
            self.assertTrue(self.hardware_owner.valid())


if __name__ == "__main__":
    unittest.main()
