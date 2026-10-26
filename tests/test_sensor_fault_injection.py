"""
Phase 3 simulated sensor fault-injection qualification.

No physical sensors, GPIO or actuators are accessed.
"""

import unittest
from unittest.mock import patch

from hypothesis import given, settings, strategies as st

from fermentalab.command_admission import (
    CommandMode,
    SimulatedCommandAdmission,
)
from fermentalab.recipes import Recipe
from fermentalab.sensors import (
    ChamberTemperatureReading,
    SimulatedChamberTemperatureSensor,
)
from fermentalab.simulation_runner import SimulationRunner
from fermentalab.supervisor import (
    SupervisoryController,
    SupervisorState,
)


def make_supervisor():
    supervisor = SupervisoryController(
        measurement_timeout_s=5.0,
        watchdog_timeout_s=20.0,
    )
    supervisor.activate(now_s=0.0)
    return supervisor


def evaluate(supervisor, reading, now_s):
    return supervisor.evaluate(
        measured_c=reading.temperature_c,
        target_c=30.0,
        measured_at_s=reading.measured_at_s,
        now_s=now_s,
    )


def make_runner():
    recipe = Recipe.from_dict({
        "schema_version": 1,
        "id": "sensor-fault-injection",
        "name": "Sensor Fault Injection",
        "stages": [
            {
                "name": "Fermentation",
                "duration_minutes": 1,
                "temperature_c": 30.0,
                "humidity_percent": None,
            }
        ],
    })

    return SimulationRunner(
        recipe,
        initial_c=25.0,
        step_s=5.0,
    )


class SensorFaultInjectionTests(unittest.TestCase):

    def setUp(self):
        self.sensor = SimulatedChamberTemperatureSensor(
            "chamber-primary"
        )

    def assert_fault_off(self, supervisor, decision):
        self.assertEqual(
            supervisor.state,
            SupervisorState.FAULT,
        )
        self.assertFalse(decision.heating_permitted)
        self.assertFalse(decision.cooling_permitted)

    def test_frozen_timestamp_eventually_faults(self):
        supervisor = make_supervisor()

        reading = self.sensor.read(
            temperature_c=25.0,
            measured_at_s=0.0,
        )

        first = evaluate(supervisor, reading, 0.0)
        self.assertTrue(first.heating_permitted)

        boundary = evaluate(supervisor, reading, 5.0)
        self.assertEqual(
            boundary.state,
            SupervisorState.ACTIVE,
        )

        expired = evaluate(supervisor, reading, 5.1)
        self.assert_fault_off(supervisor, expired)

    def test_delayed_measurement_faults(self):
        supervisor = make_supervisor()

        reading = self.sensor.read(
            temperature_c=25.0,
            measured_at_s=1.0,
        )

        decision = evaluate(supervisor, reading, 7.0)
        self.assert_fault_off(supervisor, decision)

    def test_future_measurement_faults(self):
        supervisor = make_supervisor()

        reading = self.sensor.read(
            temperature_c=25.0,
            measured_at_s=2.0,
        )

        decision = evaluate(supervisor, reading, 1.0)
        self.assert_fault_off(supervisor, decision)

    def test_out_of_order_measurement_faults(self):
        supervisor = make_supervisor()

        first = self.sensor.read(
            temperature_c=25.0,
            measured_at_s=2.0,
        )

        evaluate(supervisor, first, 2.0)

        earlier = self.sensor.read(
            temperature_c=25.0,
            measured_at_s=1.0,
        )

        decision = evaluate(supervisor, earlier, 3.0)
        self.assert_fault_off(supervisor, decision)

    def test_valid_reading_does_not_clear_fault(self):
        supervisor = make_supervisor()

        stale = self.sensor.read(
            temperature_c=25.0,
            measured_at_s=0.0,
        )

        fault = evaluate(supervisor, stale, 6.0)
        self.assert_fault_off(supervisor, fault)

        fresh = self.sensor.read(
            temperature_c=25.0,
            measured_at_s=7.0,
        )

        decision = evaluate(supervisor, fresh, 7.0)
        self.assert_fault_off(supervisor, decision)

        activation = supervisor.activate(now_s=7.0)
        self.assert_fault_off(supervisor, activation)

    def test_explicit_recovery_required(self):
        supervisor = make_supervisor()

        stale = self.sensor.read(
            temperature_c=25.0,
            measured_at_s=0.0,
        )

        evaluate(supervisor, stale, 6.0)

        cleared = supervisor.clear_fault()
        self.assertEqual(
            cleared.state,
            SupervisorState.INHIBITED,
        )
        self.assertFalse(cleared.heating_permitted)

        fresh = self.sensor.read(
            temperature_c=25.0,
            measured_at_s=7.0,
        )

        before_activation = evaluate(supervisor, fresh, 7.0)
        self.assertFalse(before_activation.heating_permitted)

        supervisor.activate(now_s=7.0)

        after_activation = evaluate(supervisor, fresh, 7.0)
        self.assertEqual(
            after_activation.state,
            SupervisorState.ACTIVE,
        )
        self.assertTrue(after_activation.heating_permitted)

    def test_sensor_read_exception_stops_simulation(self):
        with patch.object(
            SimulatedChamberTemperatureSensor,
            "read",
            side_effect=OSError("sensor disconnected"),
        ):
            with self.assertRaisesRegex(
                OSError,
                "sensor disconnected",
            ):
                make_runner().run(ambient_c=25.0)

    def test_sensor_disconnect_revokes_command_authority(self):
        admission = SimulatedCommandAdmission()

        identity = admission.acquire(
            execution_session_id="sensor-disconnect-test"
        )
        admission.enable(identity)

        pending = admission.admit(
            identity=identity,
            heating=True,
            cooling=False,
        )

        self.assertTrue(pending.accepted)
        self.assertEqual(pending.mode, CommandMode.HEATING)

        with patch.object(
            SimulatedChamberTemperatureSensor,
            "read",
            side_effect=OSError("sensor disconnected"),
        ):
            with self.assertRaisesRegex(
                OSError,
                "sensor disconnected",
            ):
                make_runner().run(
                    ambient_c=25.0,
                    command_admission=admission,
                    command_identity=identity,
                )

        self.assertFalse(admission.enabled)
        self.assertFalse(admission.is_active_identity(identity))

        rejected = admission.execute(
            identity=identity,
            decision=pending,
        )

        self.assertFalse(rejected.accepted)
        self.assertEqual(rejected.mode, CommandMode.OFF)

        resumed = admission.admit(
            identity=identity,
            heating=True,
            cooling=False,
        )

        self.assertFalse(resumed.accepted)
        self.assertEqual(resumed.mode, CommandMode.OFF)

    def test_invalid_sensor_values_rejected(self):
        for value in (
            float("nan"),
            float("inf"),
            float("-inf"),
            True,
            None,
            "25.0",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.sensor.read(
                        temperature_c=value,
                        measured_at_s=0.0,
                    )

    @settings(max_examples=100, deadline=None)
    @given(
        temperature=st.floats(
            min_value=-20.0,
            max_value=100.0,
            allow_nan=False,
            allow_infinity=False,
        ),
        timestamp=st.floats(
            min_value=0.0,
            max_value=1000.0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    def test_generated_valid_readings_preserve_values(
        self,
        temperature,
        timestamp,
    ):
        reading = self.sensor.read(
            temperature_c=temperature,
            measured_at_s=timestamp,
        )

        self.assertIsInstance(
            reading,
            ChamberTemperatureReading,
        )
        self.assertEqual(
            reading.temperature_c,
            temperature,
        )
        self.assertEqual(
            reading.measured_at_s,
            timestamp,
        )

    @settings(max_examples=100, deadline=None)
    @given(
        delay=st.floats(
            min_value=5.01,
            max_value=100.0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    def test_generated_stale_measurements_never_authorise(
        self,
        delay,
    ):
        supervisor = make_supervisor()

        reading = self.sensor.read(
            temperature_c=25.0,
            measured_at_s=0.0,
        )

        decision = evaluate(supervisor, reading, delay)

        self.assert_fault_off(supervisor, decision)


if __name__ == "__main__":
    unittest.main()
