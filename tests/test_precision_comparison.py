import unittest
from fermentalab.pi_comparison import SCENARIOS
from fermentalab.precision_comparison import simulate


class ComparisonTests(unittest.TestCase):
    def test_short_simulation(self):
        result = simulate(SCENARIOS[0], precision=True, duration_s=3600)
        self.assertTrue(0 <= result['in_band'] <= 100)
        self.assertGreaterEqual(result['heat_wh'], 0)

    def test_original_baseline_unchanged(self):
        from fermentalab.pi_comparison import simulate_pi
        original = simulate_pi(SCENARIOS[0], duration_s=3600)
        current = simulate(SCENARIOS[0], precision=False, duration_s=3600)
        self.assertAlmostEqual(original['final_food_c'], current['final'], places=9)


if __name__ == '__main__':
    unittest.main()
