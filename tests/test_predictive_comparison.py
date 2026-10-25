import unittest
from fermentalab.predictive_comparison import simulate


class ComparisonTests(unittest.TestCase):
    def test_baseline(self):
        self.assertGreater(simulate(1, duration_h=1)['heat_wh'], 0)

    def test_predictive(self):
        r = simulate(2, predictive=True, duration_h=1)
        self.assertGreaterEqual(r['overshoot_c'], 0)

    def test_model_mismatch(self):
        r = simulate(2, predictive=True, duration_h=1, model_mass=1)
        self.assertGreaterEqual(r['heat_wh'], 0)
