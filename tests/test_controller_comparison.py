import unittest
from fermentalab.controller_comparison import simulate


class TestControllerComparison(unittest.TestCase):
    def test_both_controllers_run(self):
        for method in ('hysteresis', 'fine'):
            with self.subTest(method=method):
                result = simulate(controller=method, ambient_c=25.0,
                                  target_c=30.0, duration_s=3600)
                self.assertEqual(result.controller, method)
                self.assertGreaterEqual(result.heater_energy_wh, 0)
                self.assertGreaterEqual(result.cooler_energy_wh, 0)

    def test_reproducible(self):
        a = simulate(controller='fine', ambient_c=25.0,
                     target_c=30.0, duration_s=3600)
        b = simulate(controller='fine', ambient_c=25.0,
                     target_c=30.0, duration_s=3600)
        self.assertEqual(a, b)

    def test_invalid_controller_rejected(self):
        with self.assertRaises(ValueError):
            simulate(controller='unknown', ambient_c=25.0, target_c=30.0)

    def test_duration_validation(self):
        with self.assertRaises(ValueError):
            simulate(controller='fine', ambient_c=25.0,
                     target_c=30.0, duration_s=10)


if __name__ == '__main__':
    unittest.main()
