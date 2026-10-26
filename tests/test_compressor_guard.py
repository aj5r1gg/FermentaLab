import unittest

from fermentalab.compressor_guard import CompressorGuard


class CompressorGuardTests(unittest.TestCase):

    def test_initial_restart_delay(self):
        guard = CompressorGuard(minimum_off_s=180)

        decision = guard.evaluate(
            cooling_requested=True,
            now_s=0,
        )

        self.assertFalse(decision.cooling_permitted)
        self.assertEqual(decision.remaining_off_s, 180)

        decision = guard.evaluate(
            cooling_requested=True,
            now_s=179,
        )

        self.assertFalse(decision.cooling_permitted)

        decision = guard.evaluate(
            cooling_requested=True,
            now_s=180,
        )

        self.assertTrue(decision.cooling_permitted)

    def test_restart_after_stop(self):
        guard = CompressorGuard(minimum_off_s=180)

        guard.evaluate(cooling_requested=True, now_s=0)
        guard.evaluate(cooling_requested=True, now_s=180)

        stopped = guard.evaluate(
            cooling_requested=False,
            now_s=200,
        )

        self.assertFalse(stopped.cooling_permitted)

        blocked = guard.evaluate(
            cooling_requested=True,
            now_s=379,
        )

        self.assertFalse(blocked.cooling_permitted)

        permitted = guard.evaluate(
            cooling_requested=True,
            now_s=380,
        )

        self.assertTrue(permitted.cooling_permitted)

    def test_continuous_cooling(self):
        guard = CompressorGuard(minimum_off_s=180)

        guard.evaluate(cooling_requested=True, now_s=0)
        guard.evaluate(cooling_requested=True, now_s=180)

        decision = guard.evaluate(
            cooling_requested=True,
            now_s=181,
        )

        self.assertTrue(decision.cooling_permitted)

    def test_clock_regression_rejected(self):
        guard = CompressorGuard(minimum_off_s=180)

        guard.evaluate(cooling_requested=True, now_s=100)

        with self.assertRaises(ValueError):
            guard.evaluate(
                cooling_requested=True,
                now_s=99,
            )

        self.assertFalse(guard.running)

    def test_invalid_configuration_rejected(self):
        for value in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    CompressorGuard(minimum_off_s=value)

    def test_invalid_request_rejected(self):
        guard = CompressorGuard(minimum_off_s=180)

        with self.assertRaises(TypeError):
            guard.evaluate(
                cooling_requested=1,
                now_s=0,
            )


if __name__ == "__main__":
    unittest.main()
