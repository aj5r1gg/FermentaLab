import unittest

from fermentalab.actuator_authority import ActuatorMode
from fermentalab.fermentation_runtime import (
    FermentationRuntime,
    RuntimeState,
)
from fermentalab.recipes import Recipe


def recipe():
    return Recipe.from_dict({
        "schema_version": 1,
        "id": "test-fermentation",
        "name": "Test Fermentation",
        "stages": [
            {
                "name": "Warm",
                "duration_minutes": 60,
                "temperature_c": 30.0,
                "humidity_percent": None,
            },
            {
                "name": "Cool",
                "duration_minutes": 60,
                "temperature_c": 25.0,
                "humidity_percent": None,
            },
        ],
    })


class TestFermentationRuntime(unittest.TestCase):

    def setUp(self):
        self.runtime = FermentationRuntime(recipe())

    def test_initially_inhibited(self):
        self.assertEqual(
            self.runtime.state,
            RuntimeState.INHIBITED,
        )

    def test_start_does_not_permit_actuators(self):
        result = self.runtime.start(now_s=100.0)

        self.assertEqual(
            result.state,
            RuntimeState.RUNNING,
        )
        self.assertFalse(result.heating_permitted)
        self.assertFalse(result.cooling_permitted)

    def test_first_stage_heating(self):
        self.runtime.start(now_s=100.0)

        result = self.runtime.evaluate(
            chamber_c=28.0,
            measured_at_s=100.0,
            now_s=100.0,
        )

        self.assertEqual(result.stage.name, "Warm")
        self.assertTrue(result.heating_permitted)

    def test_second_stage_cooling(self):
        self.runtime.start(now_s=100.0)

        # Maintain supervisory liveness during the simulated hour.
        for now in range(105, 3701, 5):
            self.runtime.heartbeat(now_s=float(now))

        result = self.runtime.evaluate(
            chamber_c=30.0,
            measured_at_s=3700.0,
            now_s=3700.0,
        )

        self.assertEqual(result.stage.name, "Cool")
        self.assertTrue(result.cooling_permitted)

    def test_expired_watchdog_latches_fault(self):
        self.runtime.start(now_s=100.0)

        self.runtime.heartbeat(now_s=111.0)

        self.assertEqual(
            self.runtime.state,
            RuntimeState.FAULT,
        )

        self.assertEqual(
            self.runtime.supervisor.state.value,
            "fault",
        )

    def test_heartbeat_cannot_clear_latched_fault(self):
        self.runtime.start(now_s=100.0)

        self.runtime.heartbeat(now_s=111.0)
        self.runtime.heartbeat(now_s=112.0)

        self.assertEqual(
            self.runtime.state,
            RuntimeState.FAULT,
        )

        self.assertEqual(
            self.runtime.supervisor.state.value,
            "fault",
        )

    def test_completion_disables_actuators(self):
        self.runtime.start(now_s=100.0)

        # Maintain supervisory liveness throughout the recipe.
        for now in range(105, 7301, 5):
            self.runtime.heartbeat(now_s=float(now))

        result = self.runtime.evaluate(
            chamber_c=30.0,
            measured_at_s=7300.0,
            now_s=7300.0,
        )

        self.assertEqual(
            result.state,
            RuntimeState.COMPLETED,
        )
        self.assertEqual(
            result.supervisor.actuator.mode,
            ActuatorMode.OFF,
        )
        self.assertFalse(result.heating_permitted)
        self.assertFalse(result.cooling_permitted)

    def test_completed_runtime_cannot_restart_directly(self):
        self.runtime.start(now_s=100.0)

        for now in range(105, 7301, 5):
            self.runtime.heartbeat(now_s=float(now))

        result = self.runtime.evaluate(
            chamber_c=30.0,
            measured_at_s=7300.0,
            now_s=7300.0,
        )

        self.assertEqual(
            result.state,
            RuntimeState.COMPLETED,
        )

        with self.assertRaises(RuntimeError):
            self.runtime.start(now_s=7301.0)

        self.assertEqual(
            self.runtime.state,
            RuntimeState.COMPLETED,
        )

    def test_stale_measurement_faults(self):
        self.runtime.start(now_s=100.0)

        result = self.runtime.evaluate(
            chamber_c=28.0,
            measured_at_s=90.0,
            now_s=100.0,
        )

        self.assertEqual(
            result.state,
            RuntimeState.FAULT,
        )
        self.assertFalse(result.heating_permitted)

    def test_invalid_chamber_temperature_faults(self):
        self.runtime.start(now_s=100.0)

        result = self.runtime.evaluate(
            chamber_c=float("nan"),
            measured_at_s=100.0,
            now_s=100.0,
        )

        self.assertEqual(
            result.state,
            RuntimeState.FAULT,
        )

    def test_cannot_restart_without_inhibit(self):
        self.runtime.start(now_s=100.0)

        with self.assertRaises(RuntimeError):
            self.runtime.start(now_s=101.0)

    def test_invalid_runtime_time_latches_supervisor_fault(self):
        self.runtime.start(now_s=100.0)

        result = self.runtime.evaluate(
            chamber_c=28.0,
            measured_at_s=100.0,
            now_s=float("nan"),
        )

        self.assertEqual(result.state, RuntimeState.FAULT)
        self.assertEqual(
            self.runtime.supervisor.state.value,
            "fault",
        )
        self.assertFalse(result.heating_permitted)

    def test_runtime_clock_regression_latches_fault(self):
        self.runtime.start(now_s=100.0)

        result = self.runtime.evaluate(
            chamber_c=28.0,
            measured_at_s=99.0,
            now_s=99.0,
        )

        self.assertEqual(result.state, RuntimeState.FAULT)
        self.assertEqual(
            self.runtime.supervisor.state.value,
            "fault",
        )

    def test_completion_cannot_hide_expired_watchdog(self):
        self.runtime.start(now_s=100.0)

        result = self.runtime.evaluate(
            chamber_c=30.0,
            measured_at_s=7300.0,
            now_s=7300.0,
        )

        self.assertEqual(result.state, RuntimeState.FAULT)
        self.assertEqual(
            self.runtime.supervisor.state.value,
            "fault",
        )
        self.assertFalse(result.heating_permitted)
        self.assertFalse(result.cooling_permitted)

    def test_inhibit_cannot_clear_latched_fault(self):
        self.runtime.start(now_s=100.0)

        self.runtime.heartbeat(now_s=111.0)

        result = self.runtime.inhibit()

        self.assertEqual(
            result.state,
            RuntimeState.FAULT,
        )

        self.assertEqual(
            self.runtime.supervisor.state.value,
            "fault",
        )

        self.assertFalse(result.heating_permitted)
        self.assertFalse(result.cooling_permitted)

        with self.assertRaises(RuntimeError):
            self.runtime.start(now_s=112.0)

    def test_repeated_inhibit_preserves_latched_fault(self):
        self.runtime.start(now_s=100.0)

        self.runtime.heartbeat(now_s=111.0)

        supervisor = self.runtime.supervisor

        self.assertEqual(
            self.runtime.state,
            RuntimeState.FAULT,
        )
        self.assertEqual(
            supervisor.state.value,
            "fault",
        )

        original_reason = supervisor.fault_reason
        original_generation = supervisor.authority_generation

        original_timestamps = (
            supervisor._last_now_s,
            supervisor._last_heartbeat_s,
            supervisor._last_measurement_s,
        )

        first = self.runtime.inhibit()
        second = self.runtime.inhibit()

        self.assertEqual(first.state, RuntimeState.FAULT)
        self.assertEqual(second.state, RuntimeState.FAULT)

        self.assertEqual(
            supervisor.state.value,
            "fault",
        )

        self.assertEqual(
            supervisor.fault_reason,
            original_reason,
        )

        self.assertEqual(
            supervisor.authority_generation,
            original_generation,
        )

        current_timestamps = (
            supervisor._last_now_s,
            supervisor._last_heartbeat_s,
            supervisor._last_measurement_s,
        )

        self.assertEqual(
            current_timestamps,
            original_timestamps,
        )

        for decision in (first, second):
            self.assertFalse(decision.heating_permitted)
            self.assertFalse(decision.cooling_permitted)
            self.assertEqual(
                decision.supervisor.reason,
                original_reason,
            )

        with self.assertRaises(RuntimeError):
            self.runtime.start(now_s=112.0)

        self.assertEqual(
            supervisor.authority_generation,
            original_generation,
        )

    def test_explicit_fault_clearance_requires_restart(self):
        self.runtime.start(now_s=100.0)

        self.runtime.heartbeat(now_s=111.0)

        result = self.runtime.clear_fault()

        self.assertEqual(
            result.state,
            RuntimeState.INHIBITED,
        )

        self.assertEqual(
            self.runtime.supervisor.state.value,
            "inhibited",
        )

        self.assertFalse(result.heating_permitted)
        self.assertFalse(result.cooling_permitted)

        restarted = self.runtime.start(now_s=112.0)

        self.assertEqual(
            restarted.state,
            RuntimeState.RUNNING,
        )

        self.assertFalse(restarted.heating_permitted)
        self.assertFalse(restarted.cooling_permitted)

    def test_explicit_inhibit(self):
        self.runtime.start(now_s=100.0)

        result = self.runtime.inhibit()

        self.assertEqual(
            result.state,
            RuntimeState.INHIBITED,
        )
        self.assertFalse(result.heating_permitted)


if __name__ == "__main__":
    unittest.main()
