"""
Phase 3 simulated humidity-monitoring qualification.

Ambient and chamber humidity are independently supplied,
monitoring-only values. Neither influences temperature control.

No physical sensors, GPIO or actuators are accessed.
"""

import unittest

from fermentalab.fermentation_runtime import RuntimeState
from fermentalab.recipes import Recipe
from fermentalab.sensors import (
    EnvironmentalQuantity,
    MeasurementDomain,
)
from fermentalab.simulation_runner import (
    SimulationRunner,
    SupplementarySensorConfig,
)


RECIPE_DATA = {
    "schema_version": 1,
    "id": "humidity-monitoring-test",
    "name": "Humidity Monitoring Test",
    "stages": [
        {
            "name": "Fermentation",
            "duration_minutes": 1,
            "temperature_c": 30.0,
            "humidity_percent": None,
        }
    ],
}


class SimulationHumidityTests(unittest.TestCase):

    def make_runner(self):
        return SimulationRunner(
            Recipe.from_dict(RECIPE_DATA),
            initial_c=25.0,
            step_s=5.0,
        )

    def observe(self, **kwargs):
        observations = []

        result = self.make_runner().run(
            ambient_c=35.0,
            observer=observations.append,
            report_every_s=5.0,
            **kwargs,
        )

        self.assertEqual(result.state, RuntimeState.COMPLETED)
        self.assertTrue(observations)

        return result, observations

    def test_independent_humidity_measurements(self):
        _, observations = self.observe(
            ambient_humidity_percent=15.0,
            chamber_humidity_percent=85.0,
        )

        for observation in observations:
            readings = observation.environmental_readings

            self.assertEqual(len(readings), 2)
            self.assertEqual(readings[0].value, 15.0)
            self.assertEqual(readings[1].value, 85.0)

    def test_sensor_identity_domain_and_quantity(self):
        _, observations = self.observe(
            ambient_humidity_percent=20.0,
            chamber_humidity_percent=80.0,
        )

        for observation in observations:
            ambient, chamber = observation.environmental_readings

            self.assertEqual(
                ambient.sensor_id,
                "ambient-humidity",
            )
            self.assertEqual(
                chamber.sensor_id,
                "chamber-humidity",
            )

            self.assertEqual(
                ambient.domain,
                MeasurementDomain.AMBIENT,
            )
            self.assertEqual(
                chamber.domain,
                MeasurementDomain.CHAMBER,
            )

            for reading in (ambient, chamber):
                self.assertEqual(
                    reading.quantity,
                    EnvironmentalQuantity.RELATIVE_HUMIDITY_PERCENT,
                )

    def test_periodic_measurement_timestamps(self):
        _, observations = self.observe(
            ambient_humidity_percent=25.0,
            chamber_humidity_percent=75.0,
        )

        self.assertGreater(len(observations), 1)

        for observation in observations[:-1]:
            for reading in observation.environmental_readings:
                self.assertEqual(
                    reading.measured_at_s,
                    observation.elapsed_s,
                )

    def test_final_measurement_timestamp(self):
        _, observations = self.observe(
            ambient_humidity_percent=30.0,
            chamber_humidity_percent=70.0,
        )

        final = observations[-1]

        self.assertEqual(final.elapsed_s, 60.0)
        self.assertEqual(final.stage_name, "COMPLETE")

        for reading in final.environmental_readings:
            self.assertEqual(
                reading.measured_at_s,
                60.0,
            )

    def test_individual_measurements_optional(self):
        for argument, expected_domain in (
            (
                {"ambient_humidity_percent": 10.0},
                MeasurementDomain.AMBIENT,
            ),
            (
                {"chamber_humidity_percent": 90.0},
                MeasurementDomain.CHAMBER,
            ),
        ):
            with self.subTest(argument=argument):
                _, observations = self.observe(**argument)

                for observation in observations:
                    readings = observation.environmental_readings

                    self.assertEqual(len(readings), 1)
                    self.assertEqual(
                        readings[0].domain,
                        expected_domain,
                    )

    def test_absent_humidity_produces_no_readings(self):
        _, observations = self.observe()

        for observation in observations:
            self.assertEqual(
                observation.environmental_readings,
                (),
            )

    def test_humidity_boundaries(self):
        _, observations = self.observe(
            ambient_humidity_percent=0.0,
            chamber_humidity_percent=100.0,
        )

        for observation in observations:
            readings = observation.environmental_readings

            self.assertEqual(readings[0].value, 0.0)
            self.assertEqual(readings[1].value, 100.0)

    def test_invalid_humidity_rejected(self):
        invalid_values = (
            -0.1,
            100.1,
            float("nan"),
            float("inf"),
            float("-inf"),
            True,
            False,
            "85",
            [],
        )

        for argument in (
            "ambient_humidity_percent",
            "chamber_humidity_percent",
        ):
            for value in invalid_values:
                with self.subTest(argument=argument, value=value):
                    with self.assertRaises(ValueError):
                        self.make_runner().run(
                            ambient_c=35.0,
                            **{argument: value},
                        )

    def test_humidity_does_not_change_temperature_control(self):
        baseline = self.make_runner().run(
            ambient_c=35.0,
        )

        monitored, _ = self.observe(
            ambient_humidity_percent=0.0,
            chamber_humidity_percent=100.0,
        )

        self.assertEqual(baseline.state, monitored.state)
        self.assertEqual(baseline.samples, monitored.samples)

        self.assertEqual(
            baseline.heating_seconds,
            monitored.heating_seconds,
        )
        self.assertEqual(
            baseline.cooling_seconds,
            monitored.cooling_seconds,
        )
        self.assertEqual(
            baseline.idle_seconds,
            monitored.idle_seconds,
        )

    def test_supplementary_monitoring_remains_independent(self):
        _, observations = self.observe(
            ambient_humidity_percent=15.0,
            chamber_humidity_percent=85.0,
            supplementary_chamber_sensors=(
                SupplementarySensorConfig(
                    sensor_id="chamber-secondary",
                    offset_c=0.5,
                ),
            ),
        )

        for observation in observations:
            self.assertEqual(
                len(observation.environmental_readings),
                2,
            )
            self.assertEqual(
                len(observation.supplementary_readings),
                1,
            )
            self.assertEqual(
                observation.supplementary_failures,
                (),
            )

            self.assertAlmostEqual(
                observation.supplementary_readings[0].temperature_c,
                observation.chamber_c + 0.5,
            )

            for reading in observation.environmental_readings:
                self.assertFalse(
                    hasattr(reading, "heating_permitted")
                )
                self.assertFalse(
                    hasattr(reading, "cooling_permitted")
                )


if __name__ == "__main__":
    unittest.main()
