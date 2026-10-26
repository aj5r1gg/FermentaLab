"""
FermentaLab sensor measurement interface.

Simulation-only measurement representation.

This module does not access physical sensors, GPIO,
actuators, watchdogs or independent safety hardware.

Measurement freshness and actuator permission remain
the responsibility of the existing supervisory controller.
"""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class ChamberTemperatureReading:
    sensor_id: str
    temperature_c: float
    measured_at_s: float

    def __post_init__(self):
        if (
            not isinstance(self.sensor_id, str)
            or not self.sensor_id.strip()
        ):
            raise ValueError(
                "sensor_id must be a non-empty string"
            )

        for name, value in (
            ("temperature_c", self.temperature_c),
            ("measured_at_s", self.measured_at_s),
        ):
            if (
                type(value) not in (int, float)
                or not isfinite(value)
            ):
                raise ValueError(
                    f"{name} must be finite and numeric"
                )

        if self.measured_at_s < 0:
            raise ValueError(
                "measured_at_s must be nonnegative"
            )


class SimulatedChamberTemperatureSensor:
    """
    Deterministic simulated chamber-temperature sensor.

    The caller supplies the simulated measurement and its
    timestamp. No physical sensor is accessed.
    """

    def __init__(self, sensor_id: str):
        if (
            not isinstance(sensor_id, str)
            or not sensor_id.strip()
        ):
            raise ValueError(
                "sensor_id must be a non-empty string"
            )

        self.sensor_id = sensor_id

    def read(
        self,
        *,
        temperature_c: float,
        measured_at_s: float,
    ) -> ChamberTemperatureReading:
        return ChamberTemperatureReading(
            sensor_id=self.sensor_id,
            temperature_c=temperature_c,
            measured_at_s=measured_at_s,
        )
