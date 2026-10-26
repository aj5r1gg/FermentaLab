import unittest

from fermentalab.command_admission import (
    CommandMode,
    SimulatedCommandAdmission,
)
from fermentalab.compressor_guard import CompressorGuard
from fermentalab.compressor_command import (
    execute_compressor_command,
)


class CompressorCommandTests(unittest.TestCase):

    def setUp(self):
        self.clock = 0

        self.admission = SimulatedCommandAdmission(
            clock_ns=lambda: self.clock,
        )

        self.identity = self.admission.acquire(
            execution_session_id="test-session",
        )

        self.admission.enable(self.identity)

        # Test fixture only; not a physical compressor setting.
        self.guard = CompressorGuard(minimum_off_s=5)

    def command(self, heating=False, cooling=False, now=0):
        self.clock = int(now * 1_000_000_000)

        return execute_compressor_command(
            admission=self.admission,
            identity=self.identity,
            guard=self.guard,
            heating=heating,
            cooling=cooling,
            now_s=now,
        )

    def test_initial_cooling_blocked(self):
        result = self.command(cooling=True, now=0)

        self.assertEqual(result.mode, CommandMode.OFF)
        self.assertEqual(result.remaining_off_s, 5)

    def test_cooling_permitted_after_delay(self):
        self.command(cooling=True, now=0)

        result = self.command(cooling=True, now=5)

        self.assertEqual(result.mode, CommandMode.COOLING)

    def test_restart_blocked(self):
        self.command(cooling=True, now=0)
        self.command(cooling=True, now=5)
        self.command(now=6)

        result = self.command(cooling=True, now=10)

        self.assertEqual(result.mode, CommandMode.OFF)

        result = self.command(cooling=True, now=11)

        self.assertEqual(result.mode, CommandMode.COOLING)

    def test_heating_not_delayed(self):
        result = self.command(heating=True, now=0)

        self.assertEqual(result.mode, CommandMode.HEATING)

    def test_revoked_authority_blocks_cooling(self):
        self.command(cooling=True, now=0)
        self.command(cooling=True, now=5)

        self.admission.revoke()

        result = self.command(cooling=True, now=6)

        self.assertEqual(result.mode, CommandMode.OFF)

    def test_conflicting_requests_are_off(self):
        result = self.command(
            heating=True,
            cooling=True,
            now=0,
        )

        self.assertEqual(result.mode, CommandMode.OFF)

    def test_clock_regression_latches_inhibition(self):
        self.command(cooling=True, now=100)
        self.command(cooling=True, now=105)

        result = self.command(cooling=True, now=104)

        self.assertEqual(result.mode, CommandMode.OFF)
        self.assertTrue(self.guard.faulted)

        result = self.command(cooling=True, now=110)

        self.assertEqual(result.mode, CommandMode.OFF)


if __name__ == "__main__":
    unittest.main()
