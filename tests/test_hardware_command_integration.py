"""Simulation-only hardware ownership and command admission tests."""

import tempfile
import unittest
from pathlib import Path

from fermentalab.command_admission import (
    CommandMode,
    SimulatedCommandAdmission,
)
from fermentalab.hardware_owner import HardwareOwner


class HardwareCommandIntegrationTests(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

        self.lock_path = (
            Path(self.directory.name) / "controller.lock"
        )

        self.hardware_owner = HardwareOwner(self.lock_path)

        self.admission = SimulatedCommandAdmission(
            hardware_owner=self.hardware_owner
        )

        self.identity = self.admission.acquire(
            execution_session_id="hardware-integration-test"
        )

    def admit_heating(self):
        return self.admission.admit(
            identity=self.identity,
            heating=True,
            cooling=False,
        )

    def test_enable_requires_hardware_ownership(self):
        with self.assertRaisesRegex(
            RuntimeError,
            "hardware ownership unavailable",
        ):
            self.admission.enable(self.identity)

        self.assertFalse(self.admission.enabled)

    def test_valid_ownership_permits_heating(self):
        with self.hardware_owner:
            self.admission.enable(self.identity)

            decision = self.admit_heating()

            self.assertTrue(decision.accepted)
            self.assertEqual(
                decision.mode,
                CommandMode.HEATING,
            )

            executed = self.admission.execute(
                identity=self.identity,
                decision=decision,
            )

            self.assertTrue(executed.accepted)
            self.assertEqual(
                executed.mode,
                CommandMode.HEATING,
            )

    def test_release_before_admission_rejects_on(self):
        self.hardware_owner.acquire()
        self.admission.enable(self.identity)

        self.hardware_owner.release()

        decision = self.admit_heating()

        self.assertFalse(decision.accepted)
        self.assertEqual(decision.mode, CommandMode.OFF)
        self.assertFalse(self.admission.enabled)

    def test_release_after_admission_rejects_execution(self):
        self.hardware_owner.acquire()
        self.admission.enable(self.identity)

        decision = self.admit_heating()
        self.assertTrue(decision.accepted)

        self.hardware_owner.release()

        executed = self.admission.execute(
            identity=self.identity,
            decision=decision,
        )

        self.assertFalse(executed.accepted)
        self.assertEqual(executed.mode, CommandMode.OFF)
        self.assertFalse(self.admission.enabled)

    def test_lock_file_replacement_rejects_on(self):
        with self.hardware_owner:
            self.admission.enable(self.identity)

            self.lock_path.unlink()
            self.lock_path.touch()

            decision = self.admit_heating()

            self.assertFalse(decision.accepted)
            self.assertFalse(self.admission.enabled)

    def test_parent_directory_replacement_rejects_on(self):
        root = Path(self.directory.name)

        original = root / "ownership"
        original.mkdir()

        lock_path = original / "controller.lock"

        owner = HardwareOwner(lock_path)
        admission = SimulatedCommandAdmission(
            hardware_owner=owner
        )

        identity = admission.acquire(
            execution_session_id="directory-replacement"
        )

        with owner:
            admission.enable(identity)

            original.rename(root / "displaced")
            original.mkdir()

            decision = admission.admit(
                identity=identity,
                heating=True,
                cooling=False,
            )

            self.assertFalse(decision.accepted)
            self.assertFalse(admission.enabled)

    def test_off_permitted_without_ownership(self):
        decision = self.admission.admit(
            identity=None,
            heating=False,
            cooling=False,
        )

        self.assertTrue(decision.accepted)
        self.assertEqual(decision.mode, CommandMode.OFF)

    def test_recovery_requires_fresh_command_identity(self):
        self.hardware_owner.acquire()
        self.admission.enable(self.identity)

        self.hardware_owner.release()

        rejected = self.admit_heating()
        self.assertFalse(rejected.accepted)

        self.hardware_owner.acquire()
        self.addCleanup(self.hardware_owner.release)

        with self.assertRaises(RuntimeError):
            self.admission.enable(self.identity)

        replacement = self.admission.acquire(
            execution_session_id="recovered-session"
        )

        self.admission.enable(replacement)

        decision = self.admission.admit(
            identity=replacement,
            heating=True,
            cooling=False,
        )

        self.assertTrue(decision.accepted)


if __name__ == "__main__":
    unittest.main()
