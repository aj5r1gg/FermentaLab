"""
Integration tests for simulated chamber-temperature sensing.

These tests verify the existing simulation runner consumes sensor
readings without bypassing supervisory temperature protection.
"""

import unittest
from unittest.mock import patch

from fermentalab.recipes import Recipe
from fermentalab.sensors import (
    SimulatedChamberTemperatureSensor,
)
from fermentalab.simulation_runner import SimulationRunner


RECIPE_DATA = {
    "schema_version": 1,
    "id": "sensor-integration",
    "name": "Sensor Integration",
    "stages": [
        {
            "name": "Fermentation",
            "duration_minutes": 1,
            "temperature_c": 25.0,
            "humidity_percent": None,
        }
    ],
}


class SensorRunnerIntegrationTests(unittest.TestCase):

    def make_runner(self):
        return SimulationRunner(
            Recipe.from_dict(RECIPE_DATA),
            initial_c=25.0,
            step_s=5.0,
        )

    def test_sensor_called_during_run_and_completion(self):
        original_read = SimulatedChamberTemperatureSensor.read
        calls = []

        def recording_read(sensor, *, temperature_c, measured_at_s):
            calls.append((sensor.sensor_id, measured_at_s))
            return original_read(
                sensor,
                temperature_c=temperature_c,
                measured_at_s=measured_at_s,
            )

        with patch.object(
            SimulatedChamberTemperatureSensor,
            "read",
            recording_read,
        ):
            self.make_runner().run(ambient_c=25.0)

        self.assertEqual(len(calls), 13)
        self.assertTrue(
            all(sensor_id == "chamber-primary" for sensor_id, _ in calls)
        )
        self.assertEqual(
            [timestamp for _, timestamp in calls],
            [float(value) for value in range(0, 61, 5)],
        )

    def test_sensor_temperature_affects_control(self):
        original_read = SimulatedChamberTemperatureSensor.read

        def colder_read(sensor, *, temperature_c, measured_at_s):
            return original_read(
                sensor,
                temperature_c=20.0,
                measured_at_s=measured_at_s,
            )

        with patch.object(
            SimulatedChamberTemperatureSensor,
            "read",
            colder_read,
        ):
            result = self.make_runner().run(ambient_c=25.0)

        self.assertGreater(result.heating_seconds, 0.0)

    def test_stale_sensor_timestamp_rejected(self):
        original_read = SimulatedChamberTemperatureSensor.read

        def stale_read(sensor, *, temperature_c, measured_at_s):
            return original_read(
                sensor,
                temperature_c=temperature_c,
                measured_at_s=0.0,
            )

        with patch.object(
            SimulatedChamberTemperatureSensor,
            "read",
            stale_read,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "simulation runtime stopped",
            ):
                self.make_runner().run(ambient_c=25.0)


if __name__ == "__main__":
    unittest.main()
