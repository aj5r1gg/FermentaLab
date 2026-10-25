import unittest
from fermentalab.pi_temperature_control import PITemperatureController


class TestPITemperatureController(unittest.TestCase):
    def setUp(self):
        self.c = PITemperatureController(lookahead_s=0)

    def read(self, t, temperature, target=42.0):
        return self.c.evaluate(measured_c=temperature, target_c=target,
                               observed_at_s=t, enabled=True)

    def test_initially_inhibited(self):
        d = self.c.inhibit()
        self.assertEqual((d.heating_demand, d.cooling_demand), (0, 0))

    def test_heating_reduces_near_target(self):
        far = self.read(0, 30)
        near = self.read(1, 41)
        self.assertGreater(far.heating_demand, near.heating_demand)

    def test_cooling_requested_above_target(self):
        d = self.read(0, 45)
        self.assertGreater(d.cooling_demand, 0)
        self.assertEqual(d.heating_demand, 0)

    def test_integral_increases_demand_with_persistent_error(self):
        first = self.read(0, 41)
        for t in range(1, 100):
            last = self.read(t, 41)
        self.assertGreater(last.heating_demand, first.heating_demand)

    def test_demand_bounded_and_exclusive(self):
        for t, temperature in enumerate((0, 100, 42, 39, 45)):
            d = self.read(t, temperature)
            self.assertLessEqual(max(d.heating_demand, d.cooling_demand), 1)
            self.assertFalse(d.heating_demand and d.cooling_demand)

    def test_target_change_resets_trend_and_integral(self):
        self.read(0, 40)
        self.read(1, 40)
        d = self.read(2, 40, target=30)
        self.assertEqual(d.heating_demand, 0)
        self.assertGreater(d.cooling_demand, 0)

    def test_nonmonotonic_time_inhibits(self):
        self.read(10, 40)
        d = self.read(10, 40)
        self.assertEqual((d.heating_demand, d.cooling_demand), (0, 0))

    def test_missing_observation_inhibits(self):
        self.read(0, 40)
        d = self.read(100, 40)
        self.assertEqual((d.heating_demand, d.cooling_demand), (0, 0))

    def test_invalid_input_inhibits(self):
        for bad in (True, float('nan'), float('inf')):
            self.assertEqual(self.read(0, bad).heating_demand, 0)

    def test_invalid_configuration(self):
        for bad in (0, -1, True, float('nan')):
            with self.assertRaises(ValueError):
                PITemperatureController(integral_time_s=bad)

    def test_prediction_reduces_heating_when_rising(self):
        c = PITemperatureController(lookahead_s=30)
        c.evaluate(measured_c=40, target_c=42, observed_at_s=0, enabled=True)
        d = c.evaluate(measured_c=40.2, target_c=42, observed_at_s=1, enabled=True)
        self.assertEqual(d.heating_demand, 0)

    def test_disabled_resets_integrator(self):
        self.read(0, 41)
        self.read(10, 41)
        self.c.inhibit()
        new = self.read(20, 41)
        fresh = PITemperatureController(lookahead_s=0).evaluate(
            measured_c=41, target_c=42, observed_at_s=20, enabled=True)
        self.assertEqual(new.heating_demand, fresh.heating_demand)


if __name__ == '__main__':
    unittest.main()
