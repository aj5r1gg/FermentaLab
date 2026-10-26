"""
FermentaLab sensor measurement interface.

Simulation-only measurement representation.

This module does not access physical sensors, GPIO,
actuators, watchdogs or independent safety hardware.

Measurement freshness and actuator permission remain
the responsibility of the existing supervisory controller.
"""

from dataclasses import dataclass
from enum import Enum
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


class MeasurementDomain(Enum):
    AMBIENT = "ambient"
    CHAMBER = "chamber"


class EnvironmentalQuantity(Enum):
    TEMPERATURE_C = "temperature_c"
    RELATIVE_HUMIDITY_PERCENT = "relative_humidity_percent"


@dataclass(frozen=True)
class EnvironmentalReading:
    """
    A simulated environmental measurement with explicit location.

    This representation is monitoring-only. It does not grant
    supervisory or actuator authority.
    """

    sensor_id: str
    domain: MeasurementDomain
    quantity: EnvironmentalQuantity
    value: float
    measured_at_s: float

    def __post_init__(self):
        if (
            not isinstance(self.sensor_id, str)
            or not self.sensor_id.strip()
        ):
            raise ValueError(
                "sensor_id must be a non-empty string"
            )

        if not isinstance(self.domain, MeasurementDomain):
            raise ValueError(
                "domain must be a MeasurementDomain"
            )

        if not isinstance(self.quantity, EnvironmentalQuantity):
            raise ValueError(
                "quantity must be an EnvironmentalQuantity"
            )

        if (
            type(self.value) not in (int, float)
            or not isfinite(self.value)
        ):
            raise ValueError(
                "measurement value must be finite and numeric"
            )

        if (
            type(self.measured_at_s) not in (int, float)
            or not isfinite(self.measured_at_s)
            or self.measured_at_s < 0
        ):
            raise ValueError(
                "measured_at_s must be finite and nonnegative"
            )

        if (
            self.quantity
            is EnvironmentalQuantity.RELATIVE_HUMIDITY_PERCENT
            and not 0.0 <= self.value <= 100.0
        ):
            raise ValueError(
                "relative humidity must be between 0 and 100 percent"
            )


class SimulatedEnvironmentalSensor:
    """
    Deterministic simulated environmental monitoring sensor.

    The domain and quantity are fixed at construction.

    No physical sensors or actuators are accessed.
    """

    def __init__(
        self,
        *,
        sensor_id: str,
        domain: MeasurementDomain,
        quantity: EnvironmentalQuantity,
    ):
        # Validate configuration using the same constraints
        # as an environmental reading.
        EnvironmentalReading(
            sensor_id=sensor_id,
            domain=domain,
            quantity=quantity,
            value=0.0,
            measured_at_s=0.0,
        )

        self.sensor_id = sensor_id
        self.domain = domain
        self.quantity = quantity

    def read(
        self,
        *,
        value: float,
        measured_at_s: float,
    ) -> EnvironmentalReading:
        return EnvironmentalReading(
            sensor_id=self.sensor_id,
            domain=self.domain,
            quantity=self.quantity,
            value=value,
            measured_at_s=measured_at_s,
        )
