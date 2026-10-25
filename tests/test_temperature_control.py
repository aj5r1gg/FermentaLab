import unittest

from fermentalab.temperature_control import (
    ControlMode,
    TemperatureController,
)


class TestTemperatureController(unittest.TestCase):

    def setUp(self):
        self.controller = TemperatureController(deadband_c=0.5)

    def evaluate(self, measured, target=30.0, enabled=True):
        return self.controller.evaluate(
            measured,
            target,
            enabled=enabled,
        )

    def test_initially_inhibited(self):
        self.assertEqual(
            self.controller.mode,
            ControlMode.INHIBITED,
        )

    def test_disabled_controller_is_inhibited(self):
        decision = self.evaluate(20.0, enabled=False)
        self.assertEqual(decision.mode, ControlMode.INHIBITED)

    def test_heating_requested_below_deadband(self):
        decision = self.evaluate(29.0)
        self.assertEqual(decision.mode, ControlMode.HEATING)
        self.assertTrue(decision.heating_requested)
        self.assertFalse(decision.cooling_requested)

    def test_cooling_requested_above_deadband(self):
        decision = self.evaluate(31.0)
        self.assertEqual(decision.mode, ControlMode.COOLING)
        self.assertTrue(decision.cooling_requested)
        self.assertFalse(decision.heating_requested)

    def test_idle_inside_deadband(self):
        decision = self.evaluate(30.2)
        self.assertEqual(decision.mode, ControlMode.IDLE)

    def test_heating_hysteresis(self):
        self.evaluate(29.0)

        decision = self.evaluate(29.8)
        self.assertEqual(decision.mode, ControlMode.HEATING)

        decision = self.evaluate(30.0)
        self.assertEqual(decision.mode, ControlMode.IDLE)

    def test_cooling_hysteresis(self):
        self.evaluate(31.0)

        decision = self.evaluate(30.2)
        self.assertEqual(decision.mode, ControlMode.COOLING)

        decision = self.evaluate(30.0)
        self.assertEqual(decision.mode, ControlMode.IDLE)

    def test_invalid_measurement_inhibits(self):
        self.evaluate(29.0)

        decision = self.evaluate(float("nan"))
        self.assertEqual(decision.mode, ControlMode.INHIBITED)

    def test_invalid_target_inhibits(self):
        decision = self.evaluate(30.0, float("inf"))
        self.assertEqual(decision.mode, ControlMode.INHIBITED)

    def test_boolean_measurement_rejected(self):
        decision = self.evaluate(True)
        self.assertEqual(decision.mode, ControlMode.INHIBITED)

    def test_heating_and_cooling_never_simultaneous(self):
        for measured in (20.0, 29.8, 30.0, 30.2, 40.0):
            decision = self.evaluate(measured)
            self.assertFalse(
                decision.heating_requested
                and decision.cooling_requested
            )

    def test_explicit_inhibit(self):
        self.evaluate(20.0)

        decision = self.controller.inhibit()
        self.assertEqual(decision.mode, ControlMode.INHIBITED)

    def test_invalid_deadband_rejected(self):
        for value in (0, -1, True, float("nan"), float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    TemperatureController(value)


if __name__ == "__main__":
    unittest.main()
