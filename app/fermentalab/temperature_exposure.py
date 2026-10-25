"""
Retrospective temperature exposure analysis.

Analysis only. No physical control or safety authority.

Thresholds are supplied explicitly and are not automatically
qualified fermentation or food-safety limits.

Each sample represents the interval ending at elapsed_s.
"""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class ExposureResult:
    measurement: str
    minimum_c: float
    maximum_c: float
    observed_minimum_c: float
    observed_maximum_c: float
    below_seconds: float
    within_seconds: float
    above_seconds: float
    excursion_count: int
    longest_excursion_seconds: float
    total_seconds: float


def analyse_temperature_exposure(
    samples,
    *,
    measurement,
    minimum_c,
    maximum_c,
):
    allowed_measurements = {
        "chamber_c",
        "vessel_c",
        "food_c",
    }

    if measurement not in allowed_measurements:
        raise ValueError(
            "measurement must be chamber_c, vessel_c or food_c"
        )

    for name, value in (
        ("minimum_c", minimum_c),
        ("maximum_c", maximum_c),
    ):
        if (
            type(value) not in (int, float)
            or not isfinite(value)
        ):
            raise ValueError(f"{name} must be finite")

    minimum_c = float(minimum_c)
    maximum_c = float(maximum_c)

    if minimum_c > maximum_c:
        raise ValueError(
            "minimum_c cannot exceed maximum_c"
        )

    samples = tuple(samples)

    if not samples:
        raise ValueError("samples cannot be empty")

    previous_time = 0.0
    previous_zone = "within"

    below_seconds = 0.0
    within_seconds = 0.0
    above_seconds = 0.0

    excursion_count = 0
    current_excursion_seconds = 0.0
    longest_excursion_seconds = 0.0

    observed_minimum = float("inf")
    observed_maximum = float("-inf")

    for sample in samples:
        elapsed = sample.elapsed_s
        temperature = getattr(sample, measurement)

        if (
            type(elapsed) not in (int, float)
            or not isfinite(elapsed)
            or elapsed <= previous_time
        ):
            raise ValueError(
                "sample timestamps must be finite and strictly increasing"
            )

        if (
            type(temperature) not in (int, float)
            or not isfinite(temperature)
        ):
            raise ValueError(
                "sample temperatures must be finite"
            )

        elapsed = float(elapsed)
        temperature = float(temperature)

        duration = elapsed - previous_time

        observed_minimum = min(
            observed_minimum,
            temperature,
        )

        observed_maximum = max(
            observed_maximum,
            temperature,
        )

        if temperature < minimum_c:
            zone = "below"
            below_seconds += duration

        elif temperature > maximum_c:
            zone = "above"
            above_seconds += duration

        else:
            zone = "within"
            within_seconds += duration

        if zone == "within":
            current_excursion_seconds = 0.0

        else:
            if zone != previous_zone:
                excursion_count += 1
                current_excursion_seconds = 0.0

            current_excursion_seconds += duration

            longest_excursion_seconds = max(
                longest_excursion_seconds,
                current_excursion_seconds,
            )

        previous_zone = zone
        previous_time = elapsed

    return ExposureResult(
        measurement=measurement,
        minimum_c=minimum_c,
        maximum_c=maximum_c,
        observed_minimum_c=observed_minimum,
        observed_maximum_c=observed_maximum,
        below_seconds=below_seconds,
        within_seconds=within_seconds,
        above_seconds=above_seconds,
        excursion_count=excursion_count,
        longest_excursion_seconds=longest_excursion_seconds,
        total_seconds=previous_time,
    )
