"""DS18B20 integration with existing chamber readings."""

import unittest

from fermentalab.ds18b20_reader import (
    DS18B20ChamberSensor,
    DS18B20Reader,
    SensorReadError,
)
from fermentalab.sensors import ChamberTemperatureReading


class FakeProbe:
    def __init__(self, value=25.0):
        self.value = value
        self.failure = False

    def get_temperature(self):
        if self.failure:
            raise OSError("probe disconnected")
        return self.value


class DS18B20MeasurementTests(unittest.TestCase):

    def setUp(self):
        self.probe = FakeProbe()
        self.now = 100.0
        self.reader = DS18B20Reader(
            sensor_id="28-test-probe",
            sensor=self.probe,
        )
        self.sensor = DS18B20ChamberSensor(
            reader=self.reader,
            clock=lambda: self.now,
        )

    def test_produces_existing_chamber_reading(self):
        reading = self.sensor.read()

        self.assertIsInstance(reading, ChamberTemperatureReading)
        self.assertEqual(reading.sensor_id, "28-test-probe")
        self.assertEqual(reading.temperature_c, 25.0)
        self.assertEqual(reading.measured_at_s, 100.0)

    def test_subsequent_measurement(self):
        self.sensor.read()

        self.now = 105.0
        self.probe.value = 26.5

        reading = self.sensor.read()

        self.assertEqual(reading.temperature_c, 26.5)
        self.assertEqual(reading.measured_at_s, 105.0)

    def test_disconnection_produces_no_reading(self):
        self.probe.failure = True

        with self.assertRaises(SensorReadError):
            self.sensor.read()

    def test_invalid_temperature_produces_no_reading(self):
        self.probe.value = float("nan")

        with self.assertRaises(SensorReadError):
            self.sensor.read()

    def test_regressing_timestamp_rejected(self):
        self.sensor.read()

        self.now = 99.0

        with self.assertRaises(SensorReadError):
            self.sensor.read()

    def test_repeated_timestamp_rejected(self):
        self.sensor.read()

        with self.assertRaises(SensorReadError):
            self.sensor.read()

    def test_invalid_timestamp_rejected(self):
        self.now = float("nan")

        with self.assertRaises(SensorReadError):
            self.sensor.read()

    def test_failed_reading_does_not_advance_timestamp(self):
        self.sensor.read()

        self.now = 105.0
        self.probe.failure = True

        with self.assertRaises(SensorReadError):
            self.sensor.read()

        self.probe.failure = False

        reading = self.sensor.read()

        self.assertEqual(reading.measured_at_s, 105.0)


if __name__ == "__main__":
    unittest.main()
