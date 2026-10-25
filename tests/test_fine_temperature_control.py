import unittest
from fermentalab.fine_temperature_control import FineTemperatureController


class TestFineTemperatureController(unittest.TestCase):
    def setUp(self):
        self.c = FineTemperatureController(heating_band_c=5, lookahead_s=10)

    def eval(self, temp, target=42, time=1):
        return self.c.evaluate(measured_c=temp, target_c=target,
                               observed_at_s=time, enabled=True)

    def test_initial_disabled(self):
        self.assertEqual(self.c.evaluate(measured_c=30, target_c=42,
                                        observed_at_s=1).heating_demand, 0)

    def test_far_below_target_full(self):
        self.assertEqual(self.eval(30).heating_demand, 1)

    def test_approach_reduces_demand(self):
        self.assertAlmostEqual(self.eval(40).heating_demand, 0.4)

    def test_at_target_off(self):
        self.assertEqual(self.eval(42).heating_demand, 0)

    def test_trend_reduces_demand_early(self):
        self.eval(40, time=1)
        decision = self.eval(40.5, time=11)
        self.assertAlmostEqual(decision.predicted_c, 41)
        self.assertAlmostEqual(decision.heating_demand, 0.2)

    def test_target_change_resets_trend(self):
        self.eval(40, time=1)
        decision = self.eval(40.5, target=30, time=11)
        self.assertEqual(decision.predicted_c, 40.5)
        self.assertEqual(decision.heating_demand, 0)
        self.assertTrue(decision.cooling_requested)

    def test_cooling_not_requested_while_heating(self):
        for i, temp in enumerate((30, 38, 40, 41, 42, 43), 1):
            d = self.eval(temp, time=i * 10)
            self.assertFalse(d.heating_demand > 0 and d.cooling_requested)

    def test_nonincreasing_time_inhibits(self):
        self.eval(30, time=10)
        self.assertEqual(self.eval(30, time=10).heating_demand, 0)

    def test_invalid_measurement_inhibits(self):
        self.assertEqual(self.eval(float('nan')).heating_demand, 0)

    def test_invalid_configuration(self):
        with self.assertRaises(ValueError):
            FineTemperatureController(heating_band_c=0)

    def test_inhibit_resets_history(self):
        self.eval(40, time=1)
        self.c.inhibit()
        self.assertAlmostEqual(self.eval(40.5, time=2).heating_demand, 0.3)

    def test_no_heat_when_above_target(self):
        self.assertEqual(self.eval(45).heating_demand, 0)
