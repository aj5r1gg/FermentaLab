import unittest

from fermentalab.sensors import (
    ChamberTemperatureReading,
    SimulatedChamberTemperatureSensor,
)
from fermentalab.supervisor import (
    SupervisoryController,
    SupervisorState,
)


class SensorTests(unittest.TestCase):

    def test_valid_simulated_reading(self):
        sensor = SimulatedChamberTemperatureSensor(
            "chamber-primary"
        )

        reading = sensor.read(
            temperature_c=25.5,
            measured_at_s=10.0,
        )

        self.assertIsInstance(
            reading,
            ChamberTemperatureReading,
        )
        self.assertEqual(
            reading.sensor_id,
            "chamber-primary",
        )
        self.assertEqual(reading.temperature_c, 25.5)
        self.assertEqual(reading.measured_at_s, 10.0)

    def test_invalid_temperature_rejected(self):
        sensor = SimulatedChamberTemperatureSensor(
            "chamber-primary"
        )

        for value in (
            float("nan"),
            float("inf"),
            float("-inf"),
            True,
            "25.0",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    sensor.read(
                        temperature_c=value,
                        measured_at_s=10.0,
                    )

    def test_invalid_timestamp_rejected(self):
        sensor = SimulatedChamberTemperatureSensor(
            "chamber-primary"
        )

        for value in (
            -1.0,
            float("nan"),
            float("inf"),
            True,
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    sensor.read(
                        temperature_c=25.0,
                        measured_at_s=value,
                    )

    def test_invalid_sensor_identity_rejected(self):
        for value in ("", "   ", None, 123):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    SimulatedChamberTemperatureSensor(value)

    def test_valid_reading_reaches_supervisor(self):
        sensor = SimulatedChamberTemperatureSensor(
            "chamber-primary"
        )

        supervisor = SupervisoryController()
        supervisor.activate(now_s=0.0)

        reading = sensor.read(
            temperature_c=20.0,
            measured_at_s=1.0,
        )

        decision = supervisor.evaluate(
            measured_c=reading.temperature_c,
            target_c=25.0,
            measured_at_s=reading.measured_at_s,
            now_s=1.0,
        )

        self.assertEqual(
            decision.state,
            SupervisorState.ACTIVE,
        )
        self.assertTrue(decision.heating_permitted)
        self.assertFalse(decision.cooling_permitted)

    def test_stale_reading_faults_supervisor(self):
        sensor = SimulatedChamberTemperatureSensor(
            "chamber-primary"
        )

        supervisor = SupervisoryController(
            measurement_timeout_s=5.0,
            watchdog_timeout_s=20.0,
        )

        supervisor.activate(now_s=0.0)

        reading = sensor.read(
            temperature_c=20.0,
            measured_at_s=1.0,
        )

        decision = supervisor.evaluate(
            measured_c=reading.temperature_c,
            target_c=25.0,
            measured_at_s=reading.measured_at_s,
            now_s=10.0,
        )

        self.assertEqual(
            decision.state,
            SupervisorState.FAULT,
        )
        self.assertFalse(decision.heating_permitted)
        self.assertFalse(decision.cooling_permitted)


if __name__ == "__main__":
    unittest.main()
