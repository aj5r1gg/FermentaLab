import unittest

from types import SimpleNamespace

from fermentalab.temperature_exposure import (
    analyse_temperature_exposure,
)


def sample(elapsed_s, temperature_c):
    return SimpleNamespace(
        elapsed_s=elapsed_s,
        chamber_c=temperature_c,
        vessel_c=temperature_c,
        food_c=temperature_c,
    )


class TestTemperatureExposure(unittest.TestCase):

    def analyse(self, samples, **overrides):
        arguments = {
            "measurement": "chamber_c",
            "minimum_c": 29.0,
            "maximum_c": 31.0,
        }

        arguments.update(overrides)

        return analyse_temperature_exposure(
            samples,
            **arguments,
        )

    def assert_duration_conservation(self, result):
        self.assertAlmostEqual(
            result.below_seconds
            + result.within_seconds
            + result.above_seconds,
            result.total_seconds,
        )

    def test_all_within_range(self):
        result = self.analyse([
            sample(5, 30.0),
            sample(10, 30.5),
            sample(15, 29.5),
        ])

        self.assertEqual(result.below_seconds, 0)
        self.assertEqual(result.within_seconds, 15)
        self.assertEqual(result.above_seconds, 0)
        self.assertEqual(result.excursion_count, 0)
        self.assertEqual(
            result.longest_excursion_seconds,
            0,
        )

        self.assert_duration_conservation(result)

    def test_below_minimum(self):
        result = self.analyse([
            sample(5, 28.0),
            sample(10, 28.5),
            sample(15, 30.0),
        ])

        self.assertEqual(result.below_seconds, 10)
        self.assertEqual(result.within_seconds, 5)
        self.assertEqual(result.excursion_count, 1)
        self.assertEqual(
            result.longest_excursion_seconds,
            10,
        )

        self.assert_duration_conservation(result)

    def test_above_maximum(self):
        result = self.analyse([
            sample(5, 30.0),
            sample(10, 32.0),
            sample(15, 33.0),
        ])

        self.assertEqual(result.above_seconds, 10)
        self.assertEqual(result.within_seconds, 5)
        self.assertEqual(result.excursion_count, 1)
        self.assertEqual(
            result.longest_excursion_seconds,
            10,
        )

        self.assert_duration_conservation(result)

    def test_multiple_excursions(self):
        result = self.analyse([
            sample(5, 28.0),
            sample(10, 30.0),
            sample(15, 32.0),
            sample(20, 30.0),
            sample(25, 28.0),
        ])

        self.assertEqual(result.below_seconds, 10)
        self.assertEqual(result.within_seconds, 10)
        self.assertEqual(result.above_seconds, 5)
        self.assertEqual(result.excursion_count, 3)
        self.assertEqual(
            result.longest_excursion_seconds,
            5,
        )

        self.assert_duration_conservation(result)

    def test_direct_below_to_above_transition(self):
        result = self.analyse([
            sample(5, 28.0),
            sample(10, 32.0),
        ])

        self.assertEqual(result.excursion_count, 2)
        self.assertEqual(
            result.longest_excursion_seconds,
            5,
        )

        self.assert_duration_conservation(result)

    def test_irregular_intervals(self):
        result = self.analyse([
            sample(2, 28.0),
            sample(9, 30.0),
            sample(20, 32.0),
        ])

        self.assertEqual(result.below_seconds, 2)
        self.assertEqual(result.within_seconds, 7)
        self.assertEqual(result.above_seconds, 11)
        self.assertEqual(result.total_seconds, 20)

        self.assert_duration_conservation(result)

    def test_exact_boundaries_are_within(self):
        result = self.analyse([
            sample(5, 29.0),
            sample(10, 31.0),
        ])

        self.assertEqual(result.within_seconds, 10)
        self.assertEqual(result.excursion_count, 0)

        self.assert_duration_conservation(result)

    def test_observed_extrema(self):
        result = self.analyse([
            sample(5, 28.25),
            sample(10, 32.75),
            sample(15, 30.0),
        ])

        self.assertEqual(
            result.observed_minimum_c,
            28.25,
        )

        self.assertEqual(
            result.observed_maximum_c,
            32.75,
        )

    def test_food_measurement(self):
        result = self.analyse(
            [sample(5, 32.0)],
            measurement="food_c",
        )

        self.assertEqual(result.measurement, "food_c")
        self.assertEqual(result.above_seconds, 5)

    def test_empty_samples_rejected(self):
        with self.assertRaises(ValueError):
            self.analyse([])

    def test_invalid_measurement_rejected(self):
        with self.assertRaises(ValueError):
            self.analyse(
                [sample(5, 30.0)],
                measurement="unknown",
            )

    def test_reversed_thresholds_rejected(self):
        with self.assertRaises(ValueError):
            self.analyse(
                [sample(5, 30.0)],
                minimum_c=32.0,
                maximum_c=28.0,
            )

    def test_nonfinite_threshold_rejected(self):
        for value in (
            float("nan"),
            float("inf"),
            float("-inf"),
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.analyse(
                        [sample(5, 30.0)],
                        minimum_c=value,
                    )

    def test_duplicate_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            self.analyse([
                sample(5, 30.0),
                sample(5, 30.0),
            ])

    def test_decreasing_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            self.analyse([
                sample(10, 30.0),
                sample(5, 30.0),
            ])

    def test_nonfinite_temperature_rejected(self):
        for value in (
            float("nan"),
            float("inf"),
            float("-inf"),
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.analyse([
                        sample(5, value),
                    ])

    def test_nonpositive_timestamp_rejected(self):
        for value in (0, -1):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.analyse([
                        sample(value, 30.0),
                    ])


if __name__ == "__main__":
    unittest.main()
