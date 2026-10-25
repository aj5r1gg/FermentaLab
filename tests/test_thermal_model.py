import unittest

from fermentalab.thermal_model import ThermalModel, ThermalParameters


class TestThermalModel(unittest.TestCase):
    def test_initial_equilibrium(self):
        s = ThermalModel(initial_c=30).state
        self.assertEqual((s.chamber_c, s.vessel_c, s.food_c), (30, 30, 30))

    def test_equilibrium_without_input(self):
        model = ThermalModel(initial_c=25)
        for _ in range(100):
            model.step(dt_s=1, ambient_c=25)
        self.assertEqual(model.state.food_c, 25)

    def test_heater_warms_chamber_before_food(self):
        model = ThermalModel()
        for _ in range(100):
            model.step(dt_s=1, ambient_c=25, heating_demand=1)
        s = model.state
        self.assertGreater(s.chamber_c, s.vessel_c)
        self.assertGreater(s.vessel_c, s.food_c)
        self.assertGreater(s.food_c, 25)

    def test_partial_heat_is_less_than_full_heat(self):
        half, full = ThermalModel(), ThermalModel()
        for _ in range(300):
            half.step(dt_s=1, ambient_c=25, heating_demand=0.5)
            full.step(dt_s=1, ambient_c=25, heating_demand=1)
        self.assertLess(half.state.food_c, full.state.food_c)

    def test_cooling_reduces_chamber_and_food(self):
        model = ThermalModel(initial_c=35)
        for _ in range(300):
            model.step(dt_s=1, ambient_c=35, cooling_demand=1)
        self.assertLess(model.state.chamber_c, 35)
        self.assertLess(model.state.food_c, 35)

    def test_hot_ambient_warms_unpowered_chamber(self):
        model = ThermalModel(initial_c=25)
        for _ in range(100):
            model.step(dt_s=1, ambient_c=45)
        self.assertGreater(model.state.chamber_c, 25)
        self.assertGreater(model.state.food_c, 25)

    def test_energy_accounting(self):
        model = ThermalModel()
        s = model.step(dt_s=2, ambient_c=25, heating_demand=0.25)
        self.assertAlmostEqual(s.heater_energy_j, 40)
        self.assertEqual(s.cooler_energy_j, 0)
        self.assertEqual(s.elapsed_s, 2)

    def test_internal_energy_conserved_when_insulated(self):
        p = ThermalParameters(ambient_conductance_w_per_c=0, heater_power_w=0, cooler_power_w=0)
        model = ThermalModel(parameters=p, initial_c=25)
        # Create a temperature gradient through an externally defined initial condition.
        model.state = type(model.state)(35, 25, 20)
        def energy(s):
            return (p.chamber_capacity_j_per_c * s.chamber_c +
                    p.vessel_capacity_j_per_c * s.vessel_c +
                    p.food_capacity_j_per_c * s.food_c)
        before = energy(model.state)
        for _ in range(500):
            model.step(dt_s=1, ambient_c=0)
        self.assertAlmostEqual(energy(model.state), before, places=6)

    def test_conflicting_inputs_rejected_without_state_change(self):
        model = ThermalModel()
        old = model.state
        with self.assertRaises(ValueError):
            model.step(dt_s=1, ambient_c=25, heating_demand=0.1, cooling_demand=0.1)
        self.assertEqual(model.state, old)

    def test_invalid_inputs_rejected(self):
        for kwargs in (
            dict(dt_s=0, ambient_c=25),
            dict(dt_s=6, ambient_c=25),
            dict(dt_s=True, ambient_c=25),
            dict(dt_s=1, ambient_c=float('nan')),
            dict(dt_s=1, ambient_c=25, heating_demand=-0.1),
            dict(dt_s=1, ambient_c=25, cooling_demand=1.1),
            dict(dt_s=1, ambient_c=25, heating_demand=True),
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ThermalModel().step(**kwargs)

    def test_invalid_parameters_rejected(self):
        with self.assertRaises(ValueError):
            ThermalParameters(food_capacity_j_per_c=0)
        with self.assertRaises(ValueError):
            ThermalParameters(heater_power_w=float('inf'))

    def test_elapsed_time_accumulates(self):
        model = ThermalModel()
        for _ in range(10):
            model.step(dt_s=0.5, ambient_c=25)
        self.assertEqual(model.state.elapsed_s, 5)


if __name__ == '__main__':
    unittest.main()
