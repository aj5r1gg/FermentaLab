import unittest
from fermentalab.predictive_control import PredictiveController


class PredictiveTests(unittest.TestCase):
    def test_rejects_bad_horizon(self):
        with self.assertRaises(ValueError):
            PredictiveController(horizon_s=0)

    def test_forecast_zero_heat(self):
        c = PredictiveController()
        end, maximum = c.forecast(chamber_c=45, vessel_c=43, food_c=41, heating_demand=0)
        self.assertGreater(maximum, 41)
        self.assertGreater(end, 41)

    def test_forecast_heat_increases_temperature(self):
        c = PredictiveController()
        a = c.forecast(chamber_c=40, vessel_c=40, food_c=40, heating_demand=0)[0]
        b = c.forecast(chamber_c=40, vessel_c=40, food_c=40, heating_demand=1)[0]
        self.assertGreater(b, a)

    def test_inhibit_zero(self):
        c = PredictiveController()
        d = c.evaluate(measured_c=25, target_c=42, observed_at_s=0, enabled=False)
        self.assertEqual((d.heating_demand, d.cooling_demand), (0, 0))

    def test_never_heat_and_cool_together(self):
        c = PredictiveController()
        for t in range(30):
            d = c.evaluate(measured_c=41, target_c=42, observed_at_s=t,
                           enabled=True, vessel_c=44, chamber_c=46)
            self.assertFalse(d.heating_demand and d.cooling_demand)
            self.assertTrue(0 <= d.heating_demand <= 1)
