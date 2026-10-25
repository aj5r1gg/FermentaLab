import unittest
from fermentalab.controller_diagnostics import run_diagnostics
from fermentalab.pi_comparison import SCENARIOS


class ControllerDiagnosticsTests(unittest.TestCase):
    def test_equilibrium_incubation_demand(self):
        result = run_diagnostics(SCENARIOS[0], duration_s=10)
        self.assertAlmostEqual(result['equilibrium_fraction'], 25.5 / 80)

    def test_samples_and_monotonic_time(self):
        result = run_diagnostics(SCENARIOS[0], duration_s=11, sample_every_s=5)
        self.assertEqual([r['time_h'] for r in result['samples']], [1/3600, 5/3600, 10/3600, 11/3600])

    def test_both_controllers_generate_diagnostics(self):
        for precision in (False, True):
            with self.subTest(precision=precision):
                result = run_diagnostics(SCENARIOS[1], precision=precision, duration_s=20)
                self.assertTrue(result['samples'])
                self.assertGreaterEqual(result['heat_transitions'], 0)
                self.assertGreaterEqual(result['cool_transitions'], 0)


if __name__ == '__main__':
    unittest.main()
