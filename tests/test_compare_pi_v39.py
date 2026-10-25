import unittest
from fermentalab.compare_pi_v39 import simulate_v39
from fermentalab.pi_comparison import SCENARIOS


class ComparePIv39Tests(unittest.TestCase):
    def test_incubation_reaches_target_in_model(self):
        r = simulate_v39(SCENARIOS[0])
        self.assertLess(r['last_hour_mae_c'], 0.2)
        self.assertEqual(r['last_hour_in_band_pct'], 100)

    def test_hot_ambient_reaches_target_in_model(self):
        r = simulate_v39(SCENARIOS[1])
        self.assertLess(r['last_hour_mae_c'], 0.2)

    def test_bad_duration_rejected(self):
        with self.assertRaises(ValueError):
            simulate_v39(SCENARIOS[0], duration_s=100)


if __name__ == '__main__':
    unittest.main()
