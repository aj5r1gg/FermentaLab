"""
Phase 3 supplementary monitoring failure-isolation qualification.

Expected supplementary sensor failures must not alter primary
temperature-control decisions or fabricate replacement readings.
Unexpected programming failures remain visible.
"""

import unittest
from unittest.mock import patch

from fermentalab.fermentation_runtime import RuntimeState
from fermentalab.recipes import Recipe
from fermentalab.sensors import (
    ChamberTemperatureReading,
    SimulatedChamberTemperatureSensor,
)
from fermentalab.simulation_runner import (
    SimulationRunner,
    SupplementarySensorConfig,
)


RECIPE_DATA = {
    "schema_version": 1,
    "id": "supplementary-failure-test",
    "name": "Supplementary Failure Test",
    "stages": [
        {
            "name": "Fermentation",
            "duration_minutes": 1,
            "temperature_c": 30.0,
            "humidity_percent": None,
        }
    ],
}


class SupplementarySensorFailureTests(unittest.TestCase):

    def make_runner(self):
        return SimulationRunner(
            Recipe.from_dict(RECIPE_DATA),
            initial_c=25.0,
            step_s=5.0,
        )

    def make_config(self):
        return (
            SupplementarySensorConfig(
                sensor_id="secondary-failing",
                offset_c=0.5,
            ),
            SupplementarySensorConfig(
                sensor_id="secondary-healthy",
                offset_c=-0.2,
            ),
        )

    def run_with_fault(self, fault):
        original_read = SimulatedChamberTemperatureSensor.read
        observations = []

        def injected_read(
            sensor,
            *,
            temperature_c,
            measured_at_s,
        ):
            if sensor.sensor_id == "secondary-failing":
                return fault(
                    sensor,
                    temperature_c,
                    measured_at_s,
                )

            return original_read(
                sensor,
                temperature_c=temperature_c,
                measured_at_s=measured_at_s,
            )

        with patch.object(
            SimulatedChamberTemperatureSensor,
            "read",
            injected_read,
        ):
            result = self.make_runner().run(
                ambient_c=35.0,
                supplementary_chamber_sensors=self.make_config(),
                observer=observations.append,
                report_every_s=5.0,
            )

        return result, observations

    def assert_monitoring_failure(self, fault, expected_error):
        baseline = self.make_runner().run(
            ambient_c=35.0,
        )

        result, observations = self.run_with_fault(fault)

        self.assertEqual(
            result.state,
            RuntimeState.COMPLETED,
        )

        self.assertEqual(
            result.samples,
            baseline.samples,
        )

        self.assertEqual(
            result.heating_seconds,
            baseline.heating_seconds,
        )
        self.assertEqual(
            result.cooling_seconds,
            baseline.cooling_seconds,
        )

        self.assertTrue(observations)

        for observation in observations:
            self.assertEqual(
                len(observation.supplementary_readings),
                1,
            )

            self.assertEqual(
                observation.supplementary_readings[0].sensor_id,
                "secondary-healthy",
            )

            self.assertEqual(
                len(observation.supplementary_failures),
                1,
            )

            failure = observation.supplementary_failures[0]

            self.assertEqual(
                failure.sensor_id,
                "secondary-failing",
            )

            self.assertIn(
                expected_error,
                failure.error,
            )

    def test_disconnected_supplementary_sensor(self):
        def disconnected(sensor, temperature_c, measured_at_s):
            raise OSError("supplementary sensor disconnected")

        self.assert_monitoring_failure(
            disconnected,
            "supplementary sensor disconnected",
        )

    def test_invalid_supplementary_reading_type(self):
        def invalid_type(sensor, temperature_c, measured_at_s):
            return None

        self.assert_monitoring_failure(
            invalid_type,
            "invalid supplementary reading type",
        )

    def test_wrong_supplementary_sensor_identity(self):
        def wrong_identity(sensor, temperature_c, measured_at_s):
            return ChamberTemperatureReading(
                sensor_id="different-sensor",
                temperature_c=temperature_c,
                measured_at_s=measured_at_s,
            )

        self.assert_monitoring_failure(
            wrong_identity,
            "invalid supplementary reading identity",
        )

    def test_wrong_supplementary_timestamp(self):
        def wrong_timestamp(sensor, temperature_c, measured_at_s):
            return ChamberTemperatureReading(
                sensor_id=sensor.sensor_id,
                temperature_c=temperature_c,
                measured_at_s=measured_at_s + 1.0,
            )

        self.assert_monitoring_failure(
            wrong_timestamp,
            "invalid supplementary reading identity",
        )

    def test_invalid_supplementary_temperature(self):
        def invalid_temperature(sensor, temperature_c, measured_at_s):
            return ChamberTemperatureReading(
                sensor_id=sensor.sensor_id,
                temperature_c=float("nan"),
                measured_at_s=measured_at_s,
            )

        self.assert_monitoring_failure(
            invalid_temperature,
            "temperature_c must be finite",
        )

    def test_unexpected_programming_error_propagates(self):
        original_read = SimulatedChamberTemperatureSensor.read

        def unexpected_error(
            sensor,
            *,
            temperature_c,
            measured_at_s,
        ):
            if sensor.sensor_id == "secondary-failing":
                raise RuntimeError(
                    "unexpected supplementary implementation error"
                )

            return original_read(
                sensor,
                temperature_c=temperature_c,
                measured_at_s=measured_at_s,
            )

        with patch.object(
            SimulatedChamberTemperatureSensor,
            "read",
            unexpected_error,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "unexpected supplementary implementation error",
            ):
                self.make_runner().run(
                    ambient_c=35.0,
                    supplementary_chamber_sensors=self.make_config(),
                    observer=lambda observation: None,
                )

    def test_primary_sensor_failure_still_stops_simulation(self):
        original_read = SimulatedChamberTemperatureSensor.read

        def primary_failure(
            sensor,
            *,
            temperature_c,
            measured_at_s,
        ):
            if sensor.sensor_id == "chamber-primary":
                raise OSError(
                    "primary chamber sensor disconnected"
                )

            return original_read(
                sensor,
                temperature_c=temperature_c,
                measured_at_s=measured_at_s,
            )

        with patch.object(
            SimulatedChamberTemperatureSensor,
            "read",
            primary_failure,
        ):
            with self.assertRaisesRegex(
                OSError,
                "primary chamber sensor disconnected",
            ):
                self.make_runner().run(
                    ambient_c=35.0,
                    supplementary_chamber_sensors=self.make_config(),
                    observer=lambda observation: None,
                )


if __name__ == "__main__":
    unittest.main()
