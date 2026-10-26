"""
Phase 3 supplementary chamber-temperature monitoring qualification.

Supplementary sensors are simulated, non-authoritative monitoring
inputs. They must not influence supervisory temperature control.
"""

import unittest

from fermentalab.fermentation_runtime import RuntimeState
from fermentalab.recipes import Recipe
from fermentalab.simulation_runner import (
    SimulationRunner,
    SupplementarySensorConfig,
)


RECIPE_DATA = {
    "schema_version": 1,
    "id": "supplementary-sensor-test",
    "name": "Supplementary Sensor Test",
    "stages": [
        {
            "name": "Fermentation",
            "duration_minutes": 1,
            "temperature_c": 30.0,
            "humidity_percent": None,
        }
    ],
}


class SupplementarySensorTests(unittest.TestCase):

    def make_runner(self):
        return SimulationRunner(
            Recipe.from_dict(RECIPE_DATA),
            initial_c=25.0,
            step_s=5.0,
        )

    def test_supplementary_readings_reported(self):
        observations = []

        result = self.make_runner().run(
            ambient_c=35.0,
            supplementary_chamber_sensors=(
                SupplementarySensorConfig(
                    sensor_id="chamber-secondary-a",
                    offset_c=-0.3,
                ),
                SupplementarySensorConfig(
                    sensor_id="chamber-secondary-b",
                    offset_c=0.4,
                ),
            ),
            observer=observations.append,
            report_every_s=5.0,
        )

        self.assertEqual(result.state, RuntimeState.COMPLETED)
        self.assertGreater(len(observations), 1)

        for observation in observations:
            readings = observation.supplementary_readings

            self.assertEqual(len(readings), 2)

            self.assertEqual(
                readings[0].sensor_id,
                "chamber-secondary-a",
            )
            self.assertEqual(
                readings[1].sensor_id,
                "chamber-secondary-b",
            )

            self.assertAlmostEqual(
                readings[0].temperature_c,
                observation.chamber_c - 0.3,
            )
            self.assertAlmostEqual(
                readings[1].temperature_c,
                observation.chamber_c + 0.4,
            )

            for reading in readings:
                self.assertEqual(
                    reading.measured_at_s,
                    observation.elapsed_s,
                )

    def test_supplementary_offsets_do_not_change_control(self):
        baseline = self.make_runner().run(
            ambient_c=35.0,
        )

        monitored = self.make_runner().run(
            ambient_c=35.0,
            supplementary_chamber_sensors=(
                SupplementarySensorConfig(
                    sensor_id="chamber-secondary-hot",
                    offset_c=50.0,
                ),
                SupplementarySensorConfig(
                    sensor_id="chamber-secondary-cold",
                    offset_c=-20.0,
                ),
            ),
        )

        self.assertEqual(
            baseline.state,
            monitored.state,
        )

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

        self.assertEqual(
            baseline.samples,
            monitored.samples,
        )

    def test_no_supplementary_sensors_by_default(self):
        observations = []

        self.make_runner().run(
            ambient_c=25.0,
            observer=observations.append,
        )

        self.assertTrue(observations)

        for observation in observations:
            self.assertEqual(
                observation.supplementary_readings,
                (),
            )

    def test_duplicate_sensor_identity_rejected(self):
        with self.assertRaisesRegex(
            ValueError,
            "duplicate supplementary sensor_id",
        ):
            self.make_runner().run(
                ambient_c=25.0,
                supplementary_chamber_sensors=(
                    SupplementarySensorConfig("duplicate"),
                    SupplementarySensorConfig("duplicate"),
                ),
            )

    def test_primary_sensor_identity_reserved(self):
        with self.assertRaises(ValueError):
            SupplementarySensorConfig(
                sensor_id="chamber-primary",
            )

    def test_invalid_sensor_identity_rejected(self):
        for sensor_id in ("", "   ", None, 123):
            with self.subTest(sensor_id=sensor_id):
                with self.assertRaises(ValueError):
                    SupplementarySensorConfig(
                        sensor_id=sensor_id,
                    )

    def test_invalid_offsets_rejected(self):
        for offset in (
            float("nan"),
            float("inf"),
            float("-inf"),
            True,
            None,
            "0.5",
        ):
            with self.subTest(offset=offset):
                with self.assertRaises(ValueError):
                    SupplementarySensorConfig(
                        sensor_id="secondary",
                        offset_c=offset,
                    )

    def test_configuration_must_be_tuple(self):
        with self.assertRaises(TypeError):
            self.make_runner().run(
                ambient_c=25.0,
                supplementary_chamber_sensors=[
                    SupplementarySensorConfig("secondary"),
                ],
            )

    def test_configuration_elements_validated(self):
        with self.assertRaises(TypeError):
            self.make_runner().run(
                ambient_c=25.0,
                supplementary_chamber_sensors=(
                    "secondary",
                ),
            )

    def test_zero_offset_matches_chamber(self):
        observations = []

        self.make_runner().run(
            ambient_c=25.0,
            supplementary_chamber_sensors=(
                SupplementarySensorConfig(
                    sensor_id="secondary",
                    offset_c=0.0,
                ),
            ),
            observer=observations.append,
        )

        for observation in observations:
            self.assertEqual(
                observation.supplementary_readings[0].temperature_c,
                observation.chamber_c,
            )


if __name__ == "__main__":
    unittest.main()
