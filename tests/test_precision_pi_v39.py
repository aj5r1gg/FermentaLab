import unittest
from math import isnan
from fermentalab.precision_pi_v39 import PrecisionPIv39


class PrecisionPIv39Tests(unittest.TestCase):
    def test_invalid_observation_inhibits(self):
        c = PrecisionPIv39()
        d = c.evaluate(measured_c=float('nan'), target_c=42, observed_at_s=0, enabled=True)
        self.assertEqual((d.heating_demand, d.cooling_demand), (0, 0))
        self.assertTrue(isnan(d.predicted_c))

    def test_monotonic_timestamp_required(self):
        c = PrecisionPIv39()
        c.evaluate(measured_c=25, target_c=42, observed_at_s=1, enabled=True)
        self.assertEqual(c.evaluate(measured_c=25, target_c=42, observed_at_s=1, enabled=True).reason, 'inhibited')

    def test_no_simultaneous_demands(self):
        c = PrecisionPIv39()
        for t in range(100):
            d = c.evaluate(measured_c=25 if t < 50 else 45, target_c=42,
                           observed_at_s=t, enabled=True, vessel_c=35, chamber_c=36)
            self.assertFalse(d.heating_demand > 0 and d.cooling_demand > 0)
            self.assertLessEqual(max(d.heating_demand, d.cooling_demand), 1)

    def test_integral_exceeds_old_twenty_percent_cap(self):
        c = PrecisionPIv39()
        for t in range(12000):
            c.evaluate(measured_c=41.5, target_c=42, observed_at_s=t, enabled=True)
        self.assertGreater(c._integral_demand, .2)
        self.assertLessEqual(c._integral_demand, 1)

    def test_target_change_resets_bias(self):
        c = PrecisionPIv39()
        for t in range(1000):
            c.evaluate(measured_c=41, target_c=42, observed_at_s=t, enabled=True)
        self.assertGreater(c._integral_demand, 0)
        c.evaluate(measured_c=42, target_c=42, observed_at_s=1000, enabled=True)
        c.evaluate(measured_c=42, target_c=40, observed_at_s=1001, enabled=True)
        self.assertEqual(c._integral_demand, 0)


if __name__ == '__main__':
    unittest.main()
