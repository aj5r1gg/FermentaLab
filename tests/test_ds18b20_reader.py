"""Hardware-independent DS18B20 acquisition tests."""

import unittest

from fermentalab.ds18b20_reader import (
    DS18B20Reader,
    SensorReadError,
)


class FakeSensor:
    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error

    def get_temperature(self):
        if self.error is not None:
            raise self.error
        return self.value


class DS18B20ReaderTests(unittest.TestCase):

    def test_valid_temperature(self):
        reader = DS18B20Reader(
            sensor_id="probe-1",
            sensor=FakeSensor(30.25),
        )
        self.assertEqual(reader.read_celsius(), 30.25)

    def test_disconnection(self):
        reader = DS18B20Reader(
            sensor_id="probe-1",
            sensor=FakeSensor(error=OSError("disconnected")),
        )
        with self.assertRaises(SensorReadError):
            reader.read_celsius()

    def test_nonfinite_reading(self):
        for value in (float("nan"), float("inf")):
            with self.subTest(value=value):
                reader = DS18B20Reader(
                    sensor_id="probe-1",
                    sensor=FakeSensor(value),
                )
                with self.assertRaises(SensorReadError):
                    reader.read_celsius()

    def test_out_of_range_reading(self):
        for value in (-55.1, 125.1):
            with self.subTest(value=value):
                reader = DS18B20Reader(
                    sensor_id="probe-1",
                    sensor=FakeSensor(value),
                )
                with self.assertRaises(SensorReadError):
                    reader.read_celsius()

    def test_boolean_reading_rejected(self):
        reader = DS18B20Reader(
            sensor_id="probe-1",
            sensor=FakeSensor(True),
        )
        with self.assertRaises(SensorReadError):
            reader.read_celsius()

    def test_invalid_sensor_identity(self):
        with self.assertRaises(ValueError):
            DS18B20Reader(
                sensor_id="",
                sensor=FakeSensor(30.0),
            )


if __name__ == "__main__":
    unittest.main()
