"""Tests for the experimental continuous predictive guard.

Simulation only. These tests do not establish physical safety.
"""

import unittest

from fermentalab.experimental_continuous_guard import (
    ExperimentalContinuousGuard,
)


class ExperimentalContinuousGuardTests(unittest.TestCase):

    def make_controller(self, margin=0.0):
        return ExperimentalContinuousGuard(
            guard_margin_c=margin,
            ambient_c=25.0,
        )

    def cap(self, controller, chamber, vessel, food):
        return controller.continuous_cap(
            chamber_c=chamber,
            vessel_c=vessel,
            food_c=food,
            target_c=42.0,
        )

    def evaluate(
        self,
        controller,
        time,
        food=41.5,
        vessel=42.0,
        chamber=43.0,
        enabled=True,
    ):
        return controller.evaluate(
            measured_c=food,
            target_c=42.0,
            observed_at_s=float(time),
            enabled=enabled,
            vessel_c=vessel,
            chamber_c=chamber,
        )

    def test_cold_start_allows_full_heating(self):
        controller = self.make_controller()

        cap, feasible = self.cap(
            controller, 25.0, 25.0, 25.0
        )

        self.assertTrue(feasible)
        self.assertAlmostEqual(cap, 1.0)

    def test_near_target_produces_fractional_cap(self):
        controller = self.make_controller(margin=0.05)

        cap, feasible = self.cap(
            controller, 42.0, 42.0, 42.0
        )

        self.assertTrue(feasible)
        self.assertGreater(cap, 0.3)
        self.assertLess(cap, 0.5)

    def test_continuous_cap_respects_forecast_ceiling(self):
        controller = self.make_controller(margin=0.05)

        cap, feasible = self.cap(
            controller, 45.0, 43.0, 41.5
        )

        self.assertTrue(feasible)

        _, maximum = controller.forecast(
            chamber_c=45.0,
            vessel_c=43.0,
            food_c=41.5,
            heating_demand=cap,
        )

        self.assertLessEqual(maximum, 42.0500001)

    def test_target_centred_margin_is_more_restrictive(self):
        target_controller = self.make_controller(margin=0.0)
        ceiling_controller = self.make_controller(margin=0.05)

        target_cap, target_feasible = self.cap(
            target_controller, 42.0, 42.0, 42.0
        )

        ceiling_cap, ceiling_feasible = self.cap(
            ceiling_controller, 42.0, 42.0, 42.0
        )

        self.assertTrue(target_feasible)
        self.assertTrue(ceiling_feasible)

        self.assertLess(target_cap, ceiling_cap)

    def test_infeasible_initial_temperature(self):
        controller = self.make_controller()

        cap, feasible = self.cap(
            controller, 42.1, 42.1, 42.1
        )

        self.assertFalse(feasible)
        self.assertEqual(cap, 0.0)

    def test_infeasible_stored_energy(self):
        controller = self.make_controller()

        cap, feasible = self.cap(
            controller, 60.0, 60.0, 42.0
        )

        self.assertFalse(feasible)
        self.assertEqual(cap, 0.0)

    def test_invalid_margin_rejected(self):
        for margin in (
            -0.1,
            1.1,
            float("nan"),
            float("inf"),
            True,
        ):
            with self.subTest(margin=margin):
                with self.assertRaises(ValueError):
                    self.make_controller(margin=margin)

    def test_nonfinite_forecast_input_rejected(self):
        controller = self.make_controller()

        for value in (
            float("nan"),
            float("inf"),
            float("-inf"),
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.cap(
                        controller,
                        value,
                        42.0,
                        42.0,
                    )

    def test_guard_cache_retained_for_30_seconds(self):
        controller = self.make_controller(margin=0.05)

        first = self.evaluate(
            controller,
            time=0,
        )

        self.assertEqual(first.reason, "guarded")

        initial_cap = controller._last_guard_cap
        initial_time = controller._last_guard_time

        second = self.evaluate(
            controller,
            time=1,
        )

        self.assertEqual(second.reason, "guarded-cached")
        self.assertEqual(
            controller._last_guard_cap,
            initial_cap,
        )
        self.assertEqual(
            controller._last_guard_time,
            initial_time,
        )

        third = self.evaluate(
            controller,
            time=30,
        )

        self.assertEqual(third.reason, "guarded")
        self.assertEqual(
            controller._last_guard_time,
            30.0,
        )

    def test_inhibition_clears_guard_cache(self):
        controller = self.make_controller()

        self.evaluate(
            controller,
            time=0,
        )

        self.assertIsNotNone(controller._last_guard_time)

        decision = self.evaluate(
            controller,
            time=1,
            enabled=False,
        )

        self.assertEqual(decision.reason, "inhibited")
        self.assertEqual(decision.heating_demand, 0.0)
        self.assertEqual(decision.cooling_demand, 0.0)

        self.assertIsNone(controller._last_guard_time)
        self.assertEqual(controller._last_guard_cap, 1.0)

    def test_warmup_bypasses_guard(self):
        controller = self.make_controller()

        decision = self.evaluate(
            controller,
            time=0,
            food=25.0,
            vessel=25.0,
            chamber=25.0,
        )

        self.assertEqual(decision.reason, "warmup")
        self.assertIsNone(controller._last_guard_time)

    def test_missing_thermal_state_uses_baseline(self):
        controller = self.make_controller()

        decision = controller.evaluate(
            measured_c=41.5,
            target_c=42.0,
            observed_at_s=0.0,
            enabled=True,
        )

        self.assertEqual(decision.reason, "baseline")


if __name__ == "__main__":
    unittest.main()
