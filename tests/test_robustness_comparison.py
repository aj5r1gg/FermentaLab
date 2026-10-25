"""Step 43 tests: simulation harness invariants, not accuracy acceptance."""
import unittest
from fermentalab.robustness_comparison import SCENARIOS, simulate


class RobustnessComparisonTests(unittest.TestCase):
    def test_scenarios_are_distinct(self):
        names = [s[0] for s in SCENARIOS]
        self.assertEqual(len(names), len(set(names)))
        self.assertGreaterEqual(len(names), 10)

    def test_rejects_invalid_duration(self):
        for duration in (0, 1, 25, 6.5, True):
            with self.subTest(duration=duration):
                with self.assertRaises(ValueError):
                    simulate(SCENARIOS[0], duration_h=duration)

    def test_baseline_is_deterministic(self):
        a = simulate(SCENARIOS[0], duration_h=2)
        b = simulate(SCENARIOS[0], duration_h=2)
        self.assertEqual(a, b)

    def test_predictive_metrics_bounded(self):
        r = simulate(SCENARIOS[1], predictive=True, duration_h=2)
        self.assertGreaterEqual(r['mae_c'], 0)
        self.assertGreaterEqual(r['overshoot_c'], 0)
        self.assertGreaterEqual(r['in_band_pct'], 0)
        self.assertLessEqual(r['in_band_pct'], 100)
        self.assertGreaterEqual(r['heat_wh'], 0)
        self.assertGreaterEqual(r['cool_wh'], 0)


if __name__ == '__main__':
    unittest.main()
