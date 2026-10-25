import unittest
from fermentalab.pi_comparison import Scenario, simulate_pi


class TestPIComparison(unittest.TestCase):
    def test_incubation_outputs_finite_metrics(self):
        r = simulate_pi(Scenario('incubation', 25, 42), duration_s=3600)
        self.assertTrue(0 <= r['heater_wh'] <= 80)
        self.assertGreater(r['final_food_c'], 25)

    def test_hot_ambient_requests_cooling(self):
        r = simulate_pi(Scenario('hot', 42, 30), duration_s=3600)
        self.assertGreater(r['cooler_wh'], 0)

    def test_large_batch_changes_response(self):
        a = simulate_pi(Scenario('normal', 25, 42), duration_s=3600)
        b = simulate_pi(Scenario('large', 25, 42, food_capacity_multiplier=2), duration_s=3600)
        self.assertNotAlmostEqual(a['final_food_c'], b['final_food_c'])

    def test_invalid_duration(self):
        with self.assertRaises(ValueError):
            simulate_pi(Scenario('x', 25, 42), duration_s=0)


if __name__ == '__main__':
    unittest.main()
