import unittest
from fermentalab.inertia_comparison import simulate


class ComparisonTests(unittest.TestCase):
    def test_nominal_matches_baseline(self):
        a = simulate(1, adaptive=False, duration_h=1)
        b = simulate(1, adaptive=True, duration_h=1)
        self.assertEqual(a, b)

    def test_finite_result(self):
        result = simulate(2, adaptive=True, duration_h=1)
        self.assertGreaterEqual(result['heat_wh'], 0)
        self.assertGreaterEqual(result['overshoot_c'], 0)
