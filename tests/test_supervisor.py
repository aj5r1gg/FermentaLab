import unittest

from fermentalab.actuator_authority import ActuatorMode
from fermentalab.supervisor import (
    SupervisoryController,
    SupervisorState,
)


class TestSupervisoryController(unittest.TestCase):

    def setUp(self):
        self.supervisor = SupervisoryController(
            measurement_timeout_s=5.0,
            watchdog_timeout_s=10.0,
        )

    def evaluate(
        self,
        measured=28.0,
        target=30.0,
        measured_at=100.0,
        now=100.0,
    ):
        return self.supervisor.evaluate(
            measured_c=measured,
            target_c=target,
            measured_at_s=measured_at,
            now_s=now,
        )

    def activate(self, now=100.0):
        return self.supervisor.activate(now_s=now)

    def assert_off(self, decision):
        self.assertEqual(decision.actuator.mode, ActuatorMode.OFF)
        self.assertFalse(decision.heating_permitted)
        self.assertFalse(decision.cooling_permitted)

    def test_initially_inhibited(self):
        self.assertEqual(
            self.supervisor.state,
            SupervisorState.INHIBITED,
        )

    def test_evaluation_before_activation_is_off(self):
        self.assert_off(self.evaluate())

    def test_activation_requires_measurement(self):
        self.assert_off(self.activate())
        self.assertEqual(
            self.supervisor.state,
            SupervisorState.ACTIVE,
        )

    def test_heating_permitted_with_valid_measurement(self):
        self.activate()
        decision = self.evaluate()
        self.assertTrue(decision.heating_permitted)
        self.assertFalse(decision.cooling_permitted)

    def test_cooling_permitted_with_valid_measurement(self):
        self.activate()
        decision = self.evaluate(measured=32.0)
        self.assertTrue(decision.cooling_permitted)
        self.assertFalse(decision.heating_permitted)

    def test_idle_temperature_requests_no_actuator(self):
        self.activate()
        self.assert_off(self.evaluate(measured=30.0))

    def test_stale_measurement_latches_fault(self):
        self.activate()
        decision = self.evaluate(measured_at=94.0)
        self.assert_off(decision)
        self.assertEqual(self.supervisor.state, SupervisorState.FAULT)

    def test_future_measurement_latches_fault(self):
        self.activate()
        self.assert_off(self.evaluate(measured_at=101.0))
        self.assertEqual(self.supervisor.state, SupervisorState.FAULT)

    def test_invalid_measurement_timestamp_latches_fault(self):
        self.activate()
        self.assert_off(self.evaluate(measured_at=float("nan")))
        self.assertEqual(self.supervisor.state, SupervisorState.FAULT)

    def test_invalid_temperature_latches_fault(self):
        self.activate()
        self.assert_off(self.evaluate(measured=float("nan")))
        self.assertEqual(self.supervisor.state, SupervisorState.FAULT)

    def test_invalid_target_latches_fault(self):
        self.activate()
        self.assert_off(self.evaluate(target=float("inf")))
        self.assertEqual(self.supervisor.state, SupervisorState.FAULT)

    def test_boolean_temperature_rejected(self):
        self.activate()
        self.assert_off(self.evaluate(measured=True))
        self.assertEqual(self.supervisor.state, SupervisorState.FAULT)

    def test_watchdog_expiry_latches_fault(self):
        self.activate()
        decision = self.evaluate(
            measured_at=111.0,
            now=111.0,
        )
        self.assert_off(decision)
        self.assertEqual(self.supervisor.state, SupervisorState.FAULT)

    def test_heartbeat_refreshes_watchdog(self):
        self.activate()
        self.supervisor.heartbeat(now_s=109.0)
        decision = self.evaluate(
            measured_at=115.0,
            now=115.0,
        )
        self.assertTrue(decision.heating_permitted)

    def test_late_heartbeat_cannot_resurrect_authority(self):
        self.activate()
        decision = self.supervisor.heartbeat(now_s=111.0)
        self.assert_off(decision)
        self.assertEqual(self.supervisor.state, SupervisorState.FAULT)

    def test_clock_regression_latches_fault(self):
        self.activate()
        self.evaluate(measured_at=102.0, now=102.0)
        decision = self.evaluate(
            measured_at=101.0,
            now=101.0,
        )
        self.assert_off(decision)
        self.assertEqual(self.supervisor.state, SupervisorState.FAULT)

    def test_out_of_order_measurement_latches_fault(self):
        self.activate()
        self.evaluate(measured_at=102.0, now=102.0)
        decision = self.evaluate(
            measured_at=101.0,
            now=103.0,
        )
        self.assert_off(decision)
        self.assertEqual(self.supervisor.state, SupervisorState.FAULT)

    def test_fault_requires_explicit_clearance(self):
        self.activate()
        self.evaluate(measured_at=90.0)
        self.assert_off(self.activate(now=101.0))
        self.assertEqual(self.supervisor.state, SupervisorState.FAULT)

    def test_fault_clearance_does_not_activate(self):
        self.activate()
        self.evaluate(measured_at=90.0)
        decision = self.supervisor.clear_fault()
        self.assert_off(decision)
        self.assertEqual(
            self.supervisor.state,
            SupervisorState.INHIBITED,
        )

    def test_reactivation_after_fault_clearance(self):
        self.activate()
        self.evaluate(measured_at=90.0)
        self.supervisor.clear_fault()
        self.activate(now=101.0)

        decision = self.evaluate(
            measured_at=101.0,
            now=101.0,
        )
        self.assertTrue(decision.heating_permitted)

    def test_inhibit_revokes_authority(self):
        self.activate()
        generation = self.supervisor.authority_generation
        self.assert_off(self.supervisor.inhibit())
        self.assertGreater(
            self.supervisor.authority_generation,
            generation,
        )

    def test_repeated_inhibit_remains_off(self):
        self.activate()
        self.supervisor.inhibit()
        self.assert_off(self.supervisor.inhibit())

    def test_double_activation_latches_fault(self):
        self.activate()
        self.assert_off(self.activate(now=101.0))
        self.assertEqual(self.supervisor.state, SupervisorState.FAULT)

    def test_invalid_activation_time_latches_fault(self):
        self.assert_off(self.activate(now=float("nan")))
        self.assertEqual(self.supervisor.state, SupervisorState.FAULT)

    def test_heartbeat_without_activation_is_off(self):
        self.assert_off(self.supervisor.heartbeat(now_s=100.0))

    def test_recovery_invalidates_previous_generation(self):
        self.activate()
        generation = self.supervisor.authority_generation

        self.evaluate(measured_at=90.0)
        self.supervisor.clear_fault()
        self.activate(now=101.0)

        self.assertGreater(
            self.supervisor.authority_generation,
            generation,
        )

    def test_heating_and_cooling_never_simultaneous(self):
        self.activate()

        for measured, now in (
            (20.0, 100.0),
            (30.0, 101.0),
            (40.0, 102.0),
        ):
            decision = self.evaluate(
                measured=measured,
                measured_at=now,
                now=now,
            )

            self.assertFalse(
                decision.heating_permitted
                and decision.cooling_permitted
            )

    def test_invalid_configuration_rejected(self):
        for value in (
            0,
            -1,
            True,
            float("nan"),
            float("inf"),
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    SupervisoryController(
                        measurement_timeout_s=value,
                    )

                with self.assertRaises(ValueError):
                    SupervisoryController(
                        watchdog_timeout_s=value,
                    )


if __name__ == "__main__":
    unittest.main()
