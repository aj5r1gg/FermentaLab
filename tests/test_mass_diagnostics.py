"""Regression checks for Step 40 mass diagnostics."""
import unittest
from fermentalab.mass_diagnostics import diagnose_mass


class MassDiagnosticsTests(unittest.TestCase):
    def test_default_mass_has_finite_results(self):
        r = diagnose_mass(1.0, duration_h=1)
        self.assertGreater(r.final_food_c, 25.0)
        self.assertEqual(len(r.samples), 2)
        self.assertGreater(r.heater_wh, 0)

    def test_heavier_food_warms_more_slowly(self):
        small = diagnose_mass(1.0, duration_h=1)
        large = diagnose_mass(2.0, duration_h=1)
        self.assertLess(large.final_food_c, small.final_food_c)

    def test_rejects_invalid_inputs(self):
        for multiplier in (0, -1, float('nan'), True):
            with self.subTest(multiplier=multiplier):
                with self.assertRaises(ValueError):
                    diagnose_mass(multiplier)
        with self.assertRaises(ValueError):
            diagnose_mass(1.0, duration_h=0)


if __name__ == '__main__':
    unittest.main()
