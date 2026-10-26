import unittest

from fermentalab.command_admission import (
    SimulatedCommandAdmission,
)
from fermentalab.fermentation_runtime import RuntimeState
from fermentalab.recipes import Recipe
from fermentalab.simulation_runner import SimulationRunner


def recipe(duration_minutes=10):
    return Recipe.from_dict({
        "schema_version": 1,
        "id": "simulation-test",
        "name": "Simulation Test",
        "stages": [
            {
                "name": "Fermentation",
                "duration_minutes": duration_minutes,
                "temperature_c": 30.0,
                "humidity_percent": None,
            },
        ],
    })


class TestSimulationRunner(unittest.TestCase):

    def test_completes_recipe(self):
        runner = SimulationRunner(
            recipe(),
            initial_c=25.0,
        )

        result = runner.run(ambient_c=25.0)

        self.assertEqual(
            result.state,
            RuntimeState.COMPLETED,
        )

    def test_elapsed_time_matches_recipe(self):
        runner = SimulationRunner(recipe())

        result = runner.run(ambient_c=25.0)

        self.assertAlmostEqual(
            result.samples[-1].elapsed_s,
            600.0,
        )

    def test_no_simultaneous_heating_and_cooling(self):
        runner = SimulationRunner(recipe())

        result = runner.run(ambient_c=25.0)

        for sample in result.samples:
            self.assertFalse(
                sample.heating_permitted
                and sample.cooling_permitted
            )

    def test_constant_ambient(self):
        runner = SimulationRunner(recipe())

        result = runner.run(ambient_c=25.0)

        self.assertTrue(
            all(
                sample.ambient_c == 25.0
                for sample in result.samples
            )
        )

    def test_variable_ambient(self):
        runner = SimulationRunner(recipe())

        result = runner.run(
            ambient_c=lambda second: (
                20.0 if second < 300 else 35.0
            )
        )

        self.assertTrue(
            any(
                sample.ambient_c == 20.0
                for sample in result.samples
            )
        )

        self.assertTrue(
            any(
                sample.ambient_c == 35.0
                for sample in result.samples
            )
        )

    def test_time_accounting(self):
        runner = SimulationRunner(recipe())

        result = runner.run(ambient_c=25.0)

        total = (
            result.heating_seconds
            + result.cooling_seconds
            + result.idle_seconds
        )

        self.assertAlmostEqual(total, 600.0)

    def test_invalid_step_rejected(self):
        with self.assertRaises(ValueError):
            SimulationRunner(
                recipe(),
                step_s=10.0,
            )

    def test_invalid_ambient_rejected(self):
        runner = SimulationRunner(recipe())

        with self.assertRaises(ValueError):
            runner.run(
                ambient_c=float("nan"),
            )

    def test_final_progress_is_100_percent(self):
        runner = SimulationRunner(recipe())

        result = runner.run(ambient_c=25.0)

        self.assertEqual(
            result.samples[-1].progress_percent,
            100.0,
        )

    def test_multiple_recipe_stages_complete(self):
        multi_stage_recipe = Recipe.from_dict({
            "schema_version": 1,
            "id": "multi-stage-simulation",
            "name": "Multi Stage Simulation",
            "stages": [
                {
                    "name": "Warm",
                    "duration_minutes": 5,
                    "temperature_c": 30.0,
                    "humidity_percent": None,
                },
                {
                    "name": "Cool",
                    "duration_minutes": 5,
                    "temperature_c": 25.0,
                    "humidity_percent": None,
                },
            ],
        })

        runner = SimulationRunner(multi_stage_recipe)

        result = runner.run(ambient_c=25.0)

        self.assertEqual(
            result.state,
            RuntimeState.COMPLETED,
        )

        self.assertAlmostEqual(
            result.samples[-1].elapsed_s,
            600.0,
        )

        self.assertEqual(
            result.samples[-1].progress_percent,
            100.0,
        )

        self.assertTrue(
            any(
                sample.heating_permitted
                for sample in result.samples
            )
        )

        self.assertTrue(
            any(
                sample.cooling_permitted
                for sample in result.samples
            )
        )

    def test_repeatable_simulation(self):
        runner = SimulationRunner(recipe())

        first = runner.run(ambient_c=25.0)
        second = runner.run(ambient_c=25.0)

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()


class TestSimulationCommandAdmission(unittest.TestCase):

    def make_authority(self):
        authority = SimulatedCommandAdmission()

        identity = authority.acquire(
            execution_session_id="simulation-integration"
        )

        return authority, identity

    def test_inhibited_authority_prevents_heating(self):
        authority, identity = self.make_authority()

        runner = SimulationRunner(
            recipe(duration_minutes=1),
            initial_c=20.0,
        )

        result = runner.run(
            ambient_c=20.0,
            command_admission=authority,
            command_identity=identity,
        )

        self.assertEqual(
            result.state,
            RuntimeState.COMPLETED,
        )
        self.assertEqual(result.heating_seconds, 0.0)
        self.assertEqual(result.cooling_seconds, 0.0)

    def test_enabled_authority_permits_heating(self):
        authority, identity = self.make_authority()
        authority.enable(identity)

        runner = SimulationRunner(
            recipe(duration_minutes=1),
            initial_c=20.0,
        )

        result = runner.run(
            ambient_c=20.0,
            command_admission=authority,
            command_identity=identity,
        )

        self.assertEqual(
            result.state,
            RuntimeState.COMPLETED,
        )
        self.assertGreater(result.heating_seconds, 0.0)

    def test_revocation_prevents_subsequent_heating(self):
        authority, identity = self.make_authority()
        authority.enable(identity)

        observations = []

        def observer(observation):
            observations.append(observation)

            if observation.elapsed_s >= 5.0:
                authority.revoke()

        runner = SimulationRunner(
            recipe(duration_minutes=1),
            initial_c=20.0,
        )

        result = runner.run(
            ambient_c=20.0,
            command_admission=authority,
            command_identity=identity,
            observer=observer,
            report_every_s=5.0,
        )

        self.assertEqual(
            result.state,
            RuntimeState.COMPLETED,
        )

        self.assertGreater(result.heating_seconds, 0.0)
        self.assertLess(result.heating_seconds, 60.0)

        self.assertFalse(authority.enabled)


class TestSimulationAuthorityCleanup(unittest.TestCase):

    def make_authority(self):
        authority = SimulatedCommandAdmission()

        identity = authority.acquire(
            execution_session_id="cleanup-test"
        )

        authority.enable(identity)

        return authority, identity

    def test_completion_revokes_command_authority(self):
        authority, identity = self.make_authority()

        runner = SimulationRunner(
            recipe(duration_minutes=1),
            initial_c=20.0,
        )

        result = runner.run(
            ambient_c=20.0,
            command_admission=authority,
            command_identity=identity,
        )

        self.assertEqual(
            result.state,
            RuntimeState.COMPLETED,
        )

        self.assertFalse(
            authority.enabled,
            "Command authority remained enabled after completion",
        )

        rejected = authority.admit(
            identity=identity,
            heating=True,
            cooling=False,
        )

        self.assertFalse(
            rejected.accepted,
            "Old identity admitted heating after completion",
        )

    def test_exception_revokes_command_authority(self):
        authority, identity = self.make_authority()

        runner = SimulationRunner(
            recipe(duration_minutes=1),
            initial_c=20.0,
        )

        def failing_ambient(elapsed_s):
            if elapsed_s >= 5.0:
                raise RuntimeError("Injected simulation failure")
            return 20.0

        with self.assertRaisesRegex(
            RuntimeError,
            "Injected simulation failure",
        ):
            runner.run(
                ambient_c=failing_ambient,
                command_admission=authority,
                command_identity=identity,
            )

        self.assertFalse(
            authority.enabled,
            "Command authority remained enabled after failure",
        )

        rejected = authority.admit(
            identity=identity,
            heating=True,
            cooling=False,
        )

        self.assertFalse(
            rejected.accepted,
            "Old identity admitted heating after failure",
        )
