"""Initial tests for simulated hardware-owner exclusion."""

import tempfile
import unittest
from pathlib import Path

from fermentalab.hardware_owner import (
    HardwareOwner,
    HardwareOwnershipError,
)


class HardwareOwnerTests(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

        self.lock_path = (
            Path(self.directory.name) / "controller.lock"
        )

    def test_initially_unowned(self):
        owner = HardwareOwner(self.lock_path)
        self.assertFalse(owner.acquired)

    def test_acquire_and_release(self):
        owner = HardwareOwner(self.lock_path)

        owner.acquire()
        self.assertTrue(owner.acquired)

        owner.release()
        self.assertFalse(owner.acquired)

    def test_competing_owner_rejected(self):
        first = HardwareOwner(self.lock_path)
        second = HardwareOwner(self.lock_path)

        with first:
            with self.assertRaises(HardwareOwnershipError):
                second.acquire()

            self.assertFalse(second.acquired)
            self.assertTrue(first.acquired)

    def test_reacquire_after_release(self):
        first = HardwareOwner(self.lock_path)
        second = HardwareOwner(self.lock_path)

        first.acquire()
        first.release()

        second.acquire()
        self.assertTrue(second.acquired)
        second.release()

    def test_duplicate_acquisition_rejected(self):
        owner = HardwareOwner(self.lock_path)

        with owner:
            with self.assertRaises(HardwareOwnershipError):
                owner.acquire()

            self.assertTrue(owner.acquired)

    def test_release_without_acquisition(self):
        owner = HardwareOwner(self.lock_path)

        owner.release()
        self.assertFalse(owner.acquired)


if __name__ == "__main__":
    unittest.main()


class HardwareOwnerAdversarialTests(unittest.TestCase):

    def test_lock_replacement_must_not_bypass_exclusion(self):
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "controller.lock"

            first = HardwareOwner(path)
            first.acquire()

            try:
                path.unlink()

                code = """
import sys
from fermentalab.hardware_owner import (
    HardwareOwner,
    HardwareOwnershipError,
)

try:
    with HardwareOwner(sys.argv[1]):
        sys.exit(0)
except HardwareOwnershipError:
    sys.exit(1)
"""

                result = subprocess.run(
                    [sys.executable, "-c", code, str(path)],
                    timeout=5,
                    check=False,
                )

                self.assertEqual(
                    result.returncode,
                    1,
                    "Lock-file replacement bypassed ownership exclusion",
                )
            finally:
                first.release()


class HardwareOwnerIntegrityTests(unittest.TestCase):
    """Point-in-time ownership integrity verification."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

        self.lock_path = (
            Path(self.directory.name) / "controller.lock"
        )

    def test_valid_before_acquisition(self):
        owner = HardwareOwner(self.lock_path)

        self.assertFalse(owner.valid())

    def test_valid_after_acquisition(self):
        owner = HardwareOwner(self.lock_path)

        with owner:
            self.assertTrue(owner.acquired)
            self.assertTrue(owner.valid())

    def test_invalid_after_release(self):
        owner = HardwareOwner(self.lock_path)

        owner.acquire()
        self.assertTrue(owner.valid())

        owner.release()

        self.assertFalse(owner.acquired)
        self.assertFalse(owner.valid())

    def test_lock_file_replacement_invalidates_ownership(self):
        owner = HardwareOwner(self.lock_path)

        with owner:
            self.assertTrue(owner.valid())

            self.lock_path.unlink()
            self.lock_path.touch()

            self.assertFalse(
                owner.valid(),
                "Replacement lock file retained ownership validity",
            )

    def test_parent_directory_replacement_invalidates_ownership(self):
        root = Path(self.directory.name)

        original_directory = root / "ownership"
        original_directory.mkdir()

        lock_path = original_directory / "controller.lock"

        owner = HardwareOwner(lock_path)

        with owner:
            self.assertTrue(owner.valid())

            displaced_directory = root / "ownership-displaced"

            original_directory.rename(displaced_directory)

            original_directory.mkdir()

            self.assertFalse(
                owner.valid(),
                "Replacement parent directory retained ownership validity",
            )
