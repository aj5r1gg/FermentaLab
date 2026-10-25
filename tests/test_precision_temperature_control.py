import unittest
from fermentalab.precision_temperature_control import PrecisionTemperatureController


class PrecisionTests(unittest.TestCase):
    def test_bias_persists_at_zero_error(self):
        c = PrecisionTemperatureController(lookahead_s=0)
        for t in range(300):
            c.evaluate(measured_c=41, target_c=42, observed_at_s=t, enabled=True)
        d = c.evaluate(measured_c=42, target_c=42, observed_at_s=300, enabled=True)
        self.assertGreater(d.heating_demand, 0)

    def test_exclusive_and_bounded(self):
        c = PrecisionTemperatureController()
        for t, temp in enumerate((25, 41, 42, 43, 55)):
            d = c.evaluate(measured_c=temp, target_c=42, observed_at_s=t, enabled=True)
            self.assertTrue(0 <= d.heating_demand <= 1)
            self.assertTrue(0 <= d.cooling_demand <= 1)
            self.assertFalse(d.heating_demand and d.cooling_demand)

    def test_inhibit_on_stale(self):
        c = PrecisionTemperatureController()
        c.evaluate(measured_c=40, target_c=42, observed_at_s=0, enabled=True)
        d = c.evaluate(measured_c=40, target_c=42, observed_at_s=31, enabled=True)
        self.assertEqual((d.heating_demand, d.cooling_demand), (0, 0))

    def test_invalid_thermal_measurement(self):
        c = PrecisionTemperatureController()
        d = c.evaluate(measured_c=40, target_c=42, observed_at_s=0,
                       enabled=True, vessel_c=float('nan'))
        self.assertEqual(d.reason, 'inhibited')

    def test_target_change_clears_bias(self):
        c = PrecisionTemperatureController(lookahead_s=0)
        for t in range(100):
            c.evaluate(measured_c=41, target_c=42, observed_at_s=t, enabled=True)
        changed = c.evaluate(measured_c=41, target_c=41, observed_at_s=100, enabled=True)
        self.assertEqual((changed.heating_demand, changed.cooling_demand), (0, 0))


if __name__ == '__main__':
    unittest.main()
