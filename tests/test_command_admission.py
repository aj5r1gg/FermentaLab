"""Tests for simulation-only actuator command admission."""

import unittest

from fermentalab.command_admission import (
    CommandMode,
    SimulatedCommandAdmission,
)


class CommandAdmissionTests(unittest.TestCase):

    def setUp(self):
        self.owner = SimulatedCommandAdmission()
        self.identity = self.owner.acquire(
            execution_session_id="test-session"
        )

    def test_initially_inhibited(self):
        self.assertFalse(self.owner.enabled)

        decision = self.owner.admit(
            identity=self.identity,
            heating=True,
            cooling=False,
        )

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.mode, CommandMode.OFF)

    def test_valid_heating(self):
        self.owner.enable(self.identity)

        decision = self.owner.admit(
            identity=self.identity,
            heating=True,
            cooling=False,
        )

        self.assertTrue(decision.accepted)
        self.assertEqual(decision.mode, CommandMode.HEATING)

    def test_valid_cooling(self):
        self.owner.enable(self.identity)

        decision = self.owner.admit(
            identity=self.identity,
            heating=False,
            cooling=True,
        )

        self.assertTrue(decision.accepted)
        self.assertEqual(decision.mode, CommandMode.COOLING)

    def test_conflicting_requests_rejected(self):
        self.owner.enable(self.identity)

        decision = self.owner.admit(
            identity=self.identity,
            heating=True,
            cooling=True,
        )

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.mode, CommandMode.OFF)

    def test_stale_identity_rejected(self):
        self.owner.revoke()

        replacement = self.owner.acquire(
            execution_session_id="replacement-session"
        )
        self.owner.enable(replacement)

        decision = self.owner.admit(
            identity=self.identity,
            heating=True,
            cooling=False,
        )

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.mode, CommandMode.OFF)

    def test_revocation_inhibits(self):
        self.owner.enable(self.identity)
        self.owner.revoke()

        decision = self.owner.admit(
            identity=self.identity,
            heating=True,
            cooling=False,
        )

        self.assertFalse(decision.accepted)
        self.assertFalse(self.owner.enabled)

    def test_off_permitted_without_authority(self):
        self.owner.revoke()

        decision = self.owner.admit(
            identity=None,
            heating=False,
            cooling=False,
        )

        self.assertTrue(decision.accepted)
        self.assertEqual(decision.mode, CommandMode.OFF)

    def test_invalid_request_rejected(self):
        self.owner.enable(self.identity)

        decision = self.owner.admit(
            identity=self.identity,
            heating=1,
            cooling=False,
        )

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.mode, CommandMode.OFF)

    def test_duplicate_acquisition_rejected(self):
        with self.assertRaises(RuntimeError):
            self.owner.acquire(
                execution_session_id="another-session"
            )


if __name__ == "__main__":
    unittest.main()


class CommandAdmissionAdversarialTests(unittest.TestCase):

    def test_reconstructed_identity_must_not_authorise_on(self):
        from fermentalab.command_admission import CommandIdentity

        owner = SimulatedCommandAdmission()

        original = owner.acquire(
            execution_session_id="adversarial-session"
        )
        owner.enable(original)

        reconstructed = CommandIdentity(
            controller_epoch=original.controller_epoch,
            ownership_generation=original.ownership_generation,
            inhibition_generation=original.inhibition_generation,
            execution_session_id=original.execution_session_id,
        )

        self.assertIsNot(original, reconstructed)

        decision = owner.admit(
            identity=reconstructed,
            heating=True,
            cooling=False,
        )

        self.assertFalse(
            decision.accepted,
            "Reconstructed identity authorised an ON command",
        )


class CommandExecutionAdversarialTests(unittest.TestCase):

    def test_revocation_invalidates_previously_admitted_on(self):
        owner = SimulatedCommandAdmission()

        identity = owner.acquire(
            execution_session_id="execution-race-session"
        )
        owner.enable(identity)

        admitted = owner.admit(
            identity=identity,
            heating=True,
            cooling=False,
        )

        self.assertTrue(admitted.accepted)

        owner.revoke()

        executed = owner.execute(
            identity=identity,
            decision=admitted,
        )

        self.assertFalse(
            executed.accepted,
            "Previously admitted ON executed after revocation",
        )
        self.assertEqual(executed.mode, CommandMode.OFF)


class CommandExecutionBoundaryTests(unittest.TestCase):

    def setUp(self):
        self.owner = SimulatedCommandAdmission()
        self.identity = self.owner.acquire(
            execution_session_id="boundary-session"
        )
        self.owner.enable(self.identity)

    def admit_heating(self):
        return self.owner.admit(
            identity=self.identity,
            heating=True,
            cooling=False,
        )

    def test_executed_command_cannot_be_replayed(self):
        admitted = self.admit_heating()
        self.assertTrue(admitted.accepted)

        first = self.owner.execute(
            identity=self.identity,
            decision=admitted,
        )
        second = self.owner.execute(
            identity=self.identity,
            decision=admitted,
        )

        self.assertTrue(first.accepted)
        self.assertEqual(first.mode, CommandMode.HEATING)
        self.assertFalse(second.accepted)
        self.assertEqual(second.mode, CommandMode.OFF)

    def test_fabricated_decision_cannot_execute(self):
        from fermentalab.command_admission import CommandDecision

        fabricated = CommandDecision(
            accepted=True,
            mode=CommandMode.HEATING,
            reason="simulated command admitted",
        )

        result = self.owner.execute(
            identity=self.identity,
            decision=fabricated,
        )

        self.assertFalse(result.accepted)
        self.assertEqual(result.mode, CommandMode.OFF)

    def test_old_command_rejected_after_ownership_transfer(self):
        admitted = self.admit_heating()
        self.assertTrue(admitted.accepted)

        self.owner.revoke()

        replacement = self.owner.acquire(
            execution_session_id="replacement-session"
        )
        self.owner.enable(replacement)

        result = self.owner.execute(
            identity=replacement,
            decision=admitted,
        )

        self.assertFalse(result.accepted)
        self.assertEqual(result.mode, CommandMode.OFF)

    def test_old_command_rejected_after_inhibition(self):
        admitted = self.admit_heating()
        self.assertTrue(admitted.accepted)

        self.owner.revoke()

        result = self.owner.execute(
            identity=self.identity,
            decision=admitted,
        )

        self.assertFalse(result.accepted)
        self.assertEqual(result.mode, CommandMode.OFF)


class IndependentInhibitionTests(unittest.TestCase):

    def test_inhibition_retains_ownership_and_invalidates_on(self):
        owner = SimulatedCommandAdmission()

        original = owner.acquire(
            execution_session_id="inhibition-session"
        )
        owner.enable(original)

        admitted = owner.admit(
            identity=original,
            heating=True,
            cooling=False,
        )
        self.assertTrue(admitted.accepted)

        replacement = owner.inhibit(original)

        self.assertFalse(owner.enabled)
        self.assertEqual(
            replacement.controller_epoch,
            original.controller_epoch,
        )
        self.assertEqual(
            replacement.ownership_generation,
            original.ownership_generation,
        )
        self.assertEqual(
            replacement.execution_session_id,
            original.execution_session_id,
        )
        self.assertNotEqual(
            replacement.inhibition_generation,
            original.inhibition_generation,
        )

        stale_execution = owner.execute(
            identity=original,
            decision=admitted,
        )
        self.assertFalse(stale_execution.accepted)

        with self.assertRaises(RuntimeError):
            owner.enable(original)

        owner.enable(replacement)

        stale_admission = owner.admit(
            identity=original,
            heating=True,
            cooling=False,
        )
        self.assertFalse(stale_admission.accepted)

        fresh_admission = owner.admit(
            identity=replacement,
            heating=True,
            cooling=False,
        )
        self.assertTrue(fresh_admission.accepted)

    def test_inhibition_rejects_foreign_identity(self):
        owner = SimulatedCommandAdmission()
        original = owner.acquire(
            execution_session_id="owner-session"
        )

        foreign = SimulatedCommandAdmission().acquire(
            execution_session_id="foreign-session"
        )

        with self.assertRaises(RuntimeError):
            owner.inhibit(foreign)

        self.assertFalse(owner.enabled)

        owner.enable(original)
        self.assertTrue(owner.enabled)


class CommandOrderingAdversarialTests(unittest.TestCase):

    def test_older_on_command_cannot_execute_after_newer_on(self):
        owner = SimulatedCommandAdmission()

        identity = owner.acquire(
            execution_session_id="ordering-session"
        )
        owner.enable(identity)

        older = owner.admit(
            identity=identity,
            heating=True,
            cooling=False,
        )

        newer = owner.admit(
            identity=identity,
            heating=False,
            cooling=True,
        )

        self.assertTrue(older.accepted)
        self.assertTrue(newer.accepted)

        newer_execution = owner.execute(
            identity=identity,
            decision=newer,
        )

        self.assertTrue(newer_execution.accepted)
        self.assertEqual(
            newer_execution.mode,
            CommandMode.COOLING,
        )

        older_execution = owner.execute(
            identity=identity,
            decision=older,
        )

        self.assertFalse(
            older_execution.accepted,
            "Older heating command executed after newer cooling",
        )
        self.assertEqual(
            older_execution.mode,
            CommandMode.OFF,
        )


class OffPreemptionAdversarialTests(unittest.TestCase):

    def test_off_invalidates_pending_heating(self):
        owner = SimulatedCommandAdmission()

        identity = owner.acquire(
            execution_session_id="off-preemption-session"
        )
        owner.enable(identity)

        heating = owner.admit(
            identity=identity,
            heating=True,
            cooling=False,
        )
        self.assertTrue(heating.accepted)

        off = owner.admit(
            identity=None,
            heating=False,
            cooling=False,
        )
        self.assertTrue(off.accepted)
        self.assertEqual(off.mode, CommandMode.OFF)

        stale_heating = owner.execute(
            identity=identity,
            decision=heating,
        )

        self.assertFalse(
            stale_heating.accepted,
            "Heating executed after an accepted OFF request",
        )
        self.assertEqual(stale_heating.mode, CommandMode.OFF)

    def test_off_invalidates_pending_cooling(self):
        owner = SimulatedCommandAdmission()

        identity = owner.acquire(
            execution_session_id="off-cooling-session"
        )
        owner.enable(identity)

        cooling = owner.admit(
            identity=identity,
            heating=False,
            cooling=True,
        )
        self.assertTrue(cooling.accepted)

        off = owner.admit(
            identity=None,
            heating=False,
            cooling=False,
        )
        self.assertTrue(off.accepted)

        stale_cooling = owner.execute(
            identity=identity,
            decision=cooling,
        )

        self.assertFalse(
            stale_cooling.accepted,
            "Cooling executed after an accepted OFF request",
        )
        self.assertEqual(stale_cooling.mode, CommandMode.OFF)


class CommandExpiryAdversarialTests(unittest.TestCase):

    def test_expired_on_command_cannot_execute(self):
        now_ns = [1_000_000_000]

        owner = SimulatedCommandAdmission(
            clock_ns=lambda: now_ns[0],
        )

        identity = owner.acquire(
            execution_session_id="expiry-session"
        )
        owner.enable(identity)

        admitted = owner.admit(
            identity=identity,
            heating=True,
            cooling=False,
            validity_duration_ns=100_000_000,
        )

        self.assertTrue(admitted.accepted)

        # Advance beyond the 100 ms validity period.
        now_ns[0] += 100_000_001

        executed = owner.execute(
            identity=identity,
            decision=admitted,
        )

        self.assertFalse(
            executed.accepted,
            "Expired ON command was executed",
        )
        self.assertEqual(
            executed.mode,
            CommandMode.OFF,
        )


class CommandExpiryBoundaryTests(unittest.TestCase):

    def setUp(self):
        self.now_ns = [1_000_000_000]

        self.owner = SimulatedCommandAdmission(
            clock_ns=lambda: self.now_ns[0],
        )

        self.identity = self.owner.acquire(
            execution_session_id="expiry-boundary-session"
        )
        self.owner.enable(self.identity)

    def admit_heating(self, duration_ns):
        return self.owner.admit(
            identity=self.identity,
            heating=True,
            cooling=False,
            validity_duration_ns=duration_ns,
        )

    def execute(self, decision):
        return self.owner.execute(
            identity=self.identity,
            decision=decision,
        )

    def test_execution_immediately_before_deadline(self):
        decision = self.admit_heating(100_000_000)
        self.assertTrue(decision.accepted)

        self.now_ns[0] += 99_999_999

        result = self.execute(decision)

        self.assertTrue(result.accepted)
        self.assertEqual(result.mode, CommandMode.HEATING)

    def test_execution_at_exact_deadline_rejected(self):
        decision = self.admit_heating(100_000_000)
        self.assertTrue(decision.accepted)

        self.now_ns[0] += 100_000_000

        result = self.execute(decision)

        self.assertFalse(result.accepted)
        self.assertEqual(result.mode, CommandMode.OFF)

    def test_backward_clock_rejected(self):
        decision = self.admit_heating(100_000_000)
        self.assertTrue(decision.accepted)

        self.now_ns[0] -= 1

        result = self.execute(decision)

        self.assertFalse(result.accepted)
        self.assertEqual(result.mode, CommandMode.OFF)

    def test_zero_validity_rejected(self):
        decision = self.admit_heating(0)

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.mode, CommandMode.OFF)

    def test_excessive_validity_rejected(self):
        decision = self.admit_heating(5_000_000_001)

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.mode, CommandMode.OFF)

    def test_invalid_clock_reading_rejected(self):
        self.now_ns[0] = -1

        decision = self.admit_heating(100_000_000)

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.mode, CommandMode.OFF)


class ExpiredCommandReplayTests(unittest.TestCase):

    def test_expired_command_cannot_be_revived(self):
        now_ns = [1_000_000_000]

        owner = SimulatedCommandAdmission(
            clock_ns=lambda: now_ns[0],
        )

        identity = owner.acquire(
            execution_session_id="expired-replay-session"
        )
        owner.enable(identity)

        admitted = owner.admit(
            identity=identity,
            heating=True,
            cooling=False,
            validity_duration_ns=100_000_000,
        )
        self.assertTrue(admitted.accepted)

        # Reach the exact expiry deadline.
        now_ns[0] += 100_000_000

        expired = owner.execute(
            identity=identity,
            decision=admitted,
        )
        self.assertFalse(expired.accepted)

        # Returning the clock to an earlier value must not
        # resurrect the consumed command.
        now_ns[0] -= 50_000_000

        replayed = owner.execute(
            identity=identity,
            decision=admitted,
        )

        self.assertFalse(
            replayed.accepted,
            "Expired command was resurrected",
        )
        self.assertEqual(replayed.mode, CommandMode.OFF)
