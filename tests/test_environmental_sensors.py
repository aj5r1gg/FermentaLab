"""
Phase 3 environmental measurement-domain qualification.

Simulation only. No physical sensor or actuator access.
"""

import unittest

from fermentalab.sensors import (
    EnvironmentalQuantity,
    EnvironmentalReading,
    MeasurementDomain,
    SimulatedEnvironmentalSensor,
)


class EnvironmentalSensorTests(unittest.TestCase):

    def make_sensor(self, domain, quantity):
        return SimulatedEnvironmentalSensor(
            sensor_id=f"{domain.value}-{quantity.value}",
            domain=domain,
            quantity=quantity,
        )

    def test_ambient_temperature(self):
        sensor = self.make_sensor(
            MeasurementDomain.AMBIENT,
            EnvironmentalQuantity.TEMPERATURE_C,
        )

        reading = sensor.read(
            value=43.0,
            measured_at_s=10.0,
        )

        self.assertEqual(
            reading.domain,
            MeasurementDomain.AMBIENT,
        )
        self.assertEqual(
            reading.quantity,
            EnvironmentalQuantity.TEMPERATURE_C,
        )
        self.assertEqual(reading.value, 43.0)

    def test_chamber_temperature(self):
        sensor = self.make_sensor(
            MeasurementDomain.CHAMBER,
            EnvironmentalQuantity.TEMPERATURE_C,
        )

        reading = sensor.read(
            value=30.0,
            measured_at_s=10.0,
        )

        self.assertEqual(
            reading.domain,
            MeasurementDomain.CHAMBER,
        )
        self.assertEqual(reading.value, 30.0)

    def test_ambient_relative_humidity(self):
        sensor = self.make_sensor(
            MeasurementDomain.AMBIENT,
            EnvironmentalQuantity.RELATIVE_HUMIDITY_PERCENT,
        )

        reading = sensor.read(
            value=15.0,
            measured_at_s=10.0,
        )

        self.assertEqual(
            reading.domain,
            MeasurementDomain.AMBIENT,
        )
        self.assertEqual(reading.value, 15.0)

    def test_chamber_relative_humidity(self):
        sensor = self.make_sensor(
            MeasurementDomain.CHAMBER,
            EnvironmentalQuantity.RELATIVE_HUMIDITY_PERCENT,
        )

        reading = sensor.read(
            value=85.0,
            measured_at_s=10.0,
        )

        self.assertEqual(
            reading.domain,
            MeasurementDomain.CHAMBER,
        )
        self.assertEqual(reading.value, 85.0)

    def test_humidity_boundaries(self):
        sensor = self.make_sensor(
            MeasurementDomain.CHAMBER,
            EnvironmentalQuantity.RELATIVE_HUMIDITY_PERCENT,
        )

        for value in (0.0, 100.0):
            with self.subTest(value=value):
                reading = sensor.read(
                    value=value,
                    measured_at_s=0.0,
                )
                self.assertEqual(reading.value, value)

    def test_invalid_humidity_rejected(self):
        sensor = self.make_sensor(
            MeasurementDomain.CHAMBER,
            EnvironmentalQuantity.RELATIVE_HUMIDITY_PERCENT,
        )

        for value in (
            -0.1,
            100.1,
            float("nan"),
            float("inf"),
            True,
            None,
            "85",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    sensor.read(
                        value=value,
                        measured_at_s=0.0,
                    )

    def test_invalid_timestamp_rejected(self):
        sensor = self.make_sensor(
            MeasurementDomain.AMBIENT,
            EnvironmentalQuantity.TEMPERATURE_C,
        )

        for timestamp in (
            -1.0,
            float("nan"),
            float("inf"),
            True,
            None,
        ):
            with self.subTest(timestamp=timestamp):
                with self.assertRaises(ValueError):
                    sensor.read(
                        value=25.0,
                        measured_at_s=timestamp,
                    )

    def test_invalid_domain_rejected(self):
        with self.assertRaises(ValueError):
            SimulatedEnvironmentalSensor(
                sensor_id="invalid-domain",
                domain="ambient",
                quantity=EnvironmentalQuantity.TEMPERATURE_C,
            )

    def test_invalid_quantity_rejected(self):
        with self.assertRaises(ValueError):
            SimulatedEnvironmentalSensor(
                sensor_id="invalid-quantity",
                domain=MeasurementDomain.AMBIENT,
                quantity="temperature_c",
            )

    def test_sensor_identity_preserved(self):
        sensor = SimulatedEnvironmentalSensor(
            sensor_id="ambient-monitor-1",
            domain=MeasurementDomain.AMBIENT,
            quantity=EnvironmentalQuantity.TEMPERATURE_C,
        )

        reading = sensor.read(
            value=40.0,
            measured_at_s=5.0,
        )

        self.assertEqual(
            reading.sensor_id,
            "ambient-monitor-1",
        )

    def test_reading_is_immutable(self):
        reading = EnvironmentalReading(
            sensor_id="chamber-humidity-1",
            domain=MeasurementDomain.CHAMBER,
            quantity=EnvironmentalQuantity.RELATIVE_HUMIDITY_PERCENT,
            value=80.0,
            measured_at_s=1.0,
        )

        with self.assertRaises(AttributeError):
            reading.value = 90.0

    def test_environmental_reading_has_no_actuator_authority(self):
        reading = EnvironmentalReading(
            sensor_id="ambient-temperature-1",
            domain=MeasurementDomain.AMBIENT,
            quantity=EnvironmentalQuantity.TEMPERATURE_C,
            value=45.0,
            measured_at_s=1.0,
        )

        self.assertFalse(
            hasattr(reading, "heating_permitted")
        )
        self.assertFalse(
            hasattr(reading, "cooling_permitted")
        )


if __name__ == "__main__":
    unittest.main()
