"""
FermentaLab simulated temperature decision engine.

This module produces advisory requests only.

It has no GPIO access, actuator authority, hardware ownership,
watchdog authority, or permission to energise equipment.
"""

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class ControlMode(Enum):
    INHIBITED = "inhibited"
    IDLE = "idle"
    HEATING = "heating"
    COOLING = "cooling"


@dataclass(frozen=True)
class TemperatureDecision:
    mode: ControlMode
    heating_requested: bool
    cooling_requested: bool
    reason: str


class TemperatureController:
    """
    Stateful, simulation-only temperature decision engine.

    The deadband defines the distance from the target at which
    heating or cooling begins.

    Once active, heating or cooling continues until the target
    is reached.

    Any invalid input inhibits the controller.
    """

    def __init__(self, deadband_c: float = 0.5):
        if (
            isinstance(deadband_c, bool)
            or not isinstance(deadband_c, (int, float))
            or not isfinite(deadband_c)
            or deadband_c <= 0
        ):
            raise ValueError(
                "deadband_c must be a positive finite number"
            )

        self.deadband_c = float(deadband_c)
        self._mode = ControlMode.INHIBITED
        self._last_target_c = None

    @property
    def mode(self) -> ControlMode:
        return self._mode

    def inhibit(self) -> TemperatureDecision:
        self._mode = ControlMode.INHIBITED
        return self._decision("controller inhibited")

    def evaluate(
        self,
        measured_c: float,
        target_c: float,
        *,
        enabled: bool = False,
    ) -> TemperatureDecision:

        if enabled is not True:
            return self.inhibit()

        if not self._valid_temperature(measured_c):
            return self.inhibit()

        if not self._valid_temperature(target_c):
            return self.inhibit()

        measured = float(measured_c)
        target = float(target_c)

        if self._last_target_c != target:
            self._mode = ControlMode.INHIBITED

        self._last_target_c = target

        if self._mode == ControlMode.HEATING:
            if measured >= target:
                self._mode = ControlMode.IDLE

        elif self._mode == ControlMode.COOLING:
            if measured <= target:
                self._mode = ControlMode.IDLE

        else:
            if measured <= target - self.deadband_c:
                self._mode = ControlMode.HEATING

            elif measured >= target + self.deadband_c:
                self._mode = ControlMode.COOLING

            else:
                self._mode = ControlMode.IDLE

        return self._decision("temperature evaluated")

    @staticmethod
    def _valid_temperature(value) -> bool:
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and isfinite(value)
        )

    def _decision(self, reason: str) -> TemperatureDecision:
        return TemperatureDecision(
            mode=self._mode,
            heating_requested=self._mode == ControlMode.HEATING,
            cooling_requested=self._mode == ControlMode.COOLING,
            reason=reason,
        )
