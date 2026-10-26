"""End-to-end simulation-only compressor restart protection."""

import unittest

from fermentalab.command_admission import SimulatedCommandAdmission
from fermentalab.compressor_guard import CompressorGuard
from fermentalab.fermentation_runtime import RuntimeState
from fermentalab.recipes import Recipe
from fermentalab.simulation_runner import SimulationRunner


def cooling_recipe():
    return Recipe.from_dict({
        "schema_version": 1,
        "id": "compressor-integration-test",
        "name": "Compressor Integration Test",
        "stages": [
            {
                "name": "Cooling",
                "duration_minutes": 1,
                "temperature_c": 20.0,
                "humidity_percent": None,
            },
        ],
    })


class CompressorRunnerIntegrationTests(unittest.TestCase):

    def setUp(self):
        self.runner = SimulationRunner(
            cooling_recipe(),
            initial_c=35.0,
            step_s=5.0,
        )

        self.admission = SimulatedCommandAdmission()

        self.identity = self.admission.acquire(
            execution_session_id="compressor-runner-test",
        )

    def run_simulation(self, *, guard, enable=True):
        observations = []

        if enable:
            self.admission.enable(self.identity)

        result = self.runner.run(
            ambient_c=35.0,
            command_admission=self.admission,
            command_identity=self.identity,
            compressor_guard=guard,
            observer=observations.append,
            report_every_s=5.0,
        )

        return result, observations

    def test_initial_delay_then_cooling(self):
        guard = CompressorGuard(minimum_off_s=15)

        result, observations = self.run_simulation(guard=guard)

        self.assertEqual(result.state, RuntimeState.COMPLETED)

        initial = [
            observation
            for observation in observations
            if observation.elapsed_s < 15
        ]

        self.assertTrue(initial)

        self.assertTrue(
            all(
                not observation.cooling_permitted
                for observation in initial
            )
        )

        self.assertTrue(
            any(
                observation.cooling_permitted
                for observation in observations
                if observation.elapsed_s >= 15
            )
        )

        self.assertGreater(result.cooling_seconds, 0)

    def test_long_delay_prevents_cooling(self):
        guard = CompressorGuard(minimum_off_s=120)

        result, observations = self.run_simulation(guard=guard)

        self.assertEqual(result.state, RuntimeState.COMPLETED)
        self.assertEqual(result.cooling_seconds, 0)

        self.assertTrue(
            all(
                not observation.cooling_permitted
                for observation in observations
            )
        )

    def test_inhibited_admission_prevents_cooling(self):
        guard = CompressorGuard(minimum_off_s=5)

        result, observations = self.run_simulation(
            guard=guard,
            enable=False,
        )

        self.assertEqual(result.state, RuntimeState.COMPLETED)
        self.assertEqual(result.cooling_seconds, 0)

        self.assertTrue(
            all(
                not observation.cooling_permitted
                for observation in observations
            )
        )

    def test_guard_requires_command_admission(self):
        with self.assertRaises(ValueError):
            self.runner.run(
                ambient_c=35.0,
                compressor_guard=CompressorGuard(
                    minimum_off_s=15,
                ),
            )

    def test_previously_used_guard_rejected(self):
        guard = CompressorGuard(minimum_off_s=15)

        self.run_simulation(guard=guard)

        self.assertTrue(guard.used)

        new_admission = SimulatedCommandAdmission()

        new_identity = new_admission.acquire(
            execution_session_id="second-simulation",
        )

        new_admission.enable(new_identity)

        with self.assertRaisesRegex(
            ValueError,
            "compressor_guard must be unused",
        ):
            self.runner.run(
                ambient_c=35.0,
                command_admission=new_admission,
                command_identity=new_identity,
                compressor_guard=guard,
            )


if __name__ == "__main__":
    unittest.main()
