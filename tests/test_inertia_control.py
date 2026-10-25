import unittest
from fermentalab.inertia_control import InertiaAwareController


class InertiaTests(unittest.TestCase):
    def test_invalid_multiplier(self):
        with self.assertRaises(ValueError):
            InertiaAwareController(food_capacity_multiplier=0)

    def test_nominal_gains_preserved(self):
        c = InertiaAwareController(food_capacity_multiplier=1)
        self.assertEqual(c.base.vessel_prediction_gain, 0.25)
        self.assertEqual(c.base.chamber_prediction_gain, 0.05)

    def test_larger_mass_increases_prediction(self):
        a = InertiaAwareController(food_capacity_multiplier=1)
        b = InertiaAwareController(food_capacity_multiplier=2)
        args = dict(measured_c=40, target_c=42, observed_at_s=0,
                    enabled=True, vessel_c=44, chamber_c=46)
        self.assertGreater(b.evaluate(**args).predicted_c, a.evaluate(**args).predicted_c)

    def test_inhibition(self):
        d = InertiaAwareController().evaluate(measured_c=40, target_c=42,
                                              observed_at_s=0, enabled=False)
        self.assertEqual((d.heating_demand, d.cooling_demand), (0, 0))
