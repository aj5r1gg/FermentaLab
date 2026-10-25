"""
FermentaLab simulated supervisory controller.

This module coordinates advisory temperature control and simulated
actuator authority.

It does not operate GPIO, relays, mains equipment, or a physical
watchdog. It is not a substitute for independent hardware safety.
"""

from dataclasses import dataclass
from enum import Enum
from math import isfinite

from fermentalab.actuator_authority import (
    ActuatorAuthority,
    ActuatorDecision,
    ActuatorMode,
)
from fermentalab.temperature_control import TemperatureController


class SupervisorState(Enum):
    INHIBITED = "inhibited"
    ACTIVE = "active"
    FAULT = "fault"


@dataclass(frozen=True)
class SupervisorDecision:
    state: SupervisorState
    actuator: ActuatorDecision
    reason: str

    @property
    def heating_permitted(self) -> bool:
        return self.actuator.heating_permitted

    @property
    def cooling_permitted(self) -> bool:
        return self.actuator.cooling_permitted


class SupervisoryController:
    """
    Deterministic, simulation-only supervisory controller.

    All timestamps must use the same monotonic timebase.

    A watchdog heartbeat confirms supervisory liveness; it does not
    establish measurement freshness.

    Faults are latched. Recovery requires explicit fault clearance
    followed by a new activation.
    """

    def __init__(
        self,
        *,
        measurement_timeout_s: float = 5.0,
        watchdog_timeout_s: float = 10.0,
        deadband_c: float = 0.5,
    ):
        self._measurement_timeout_s = self._positive_finite(
            measurement_timeout_s,
            "measurement_timeout_s",
        )
        self._watchdog_timeout_s = self._positive_finite(
            watchdog_timeout_s,
            "watchdog_timeout_s",
        )

        self._controller = TemperatureController(
            deadband_c=deadband_c,
        )
        self._authority = ActuatorAuthority()

        self._state = SupervisorState.INHIBITED
        self._fault_reason = None
        self._token = None
        self._last_heartbeat_s = None
        self._last_now_s = None
        self._last_measurement_s = None

    @property
    def state(self) -> SupervisorState:
        return self._state

    @property
    def fault_reason(self) -> str | None:
        return self._fault_reason

    @property
    def authority_generation(self) -> int:
        return self._authority.generation

    @staticmethod
    def _valid_number(value) -> bool:
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and isfinite(value)
        )

    @classmethod
    def _positive_finite(cls, value, name: str) -> float:
        if not cls._valid_number(value) or value <= 0:
            raise ValueError(f"{name} must be positive and finite")
        return float(value)

    def _accept_time(self, now_s) -> bool:
        if not self._valid_number(now_s):
            return False

        now = float(now_s)

        if self._last_now_s is not None and now < self._last_now_s:
            return False

        self._last_now_s = now
        return True

    def _off(self, reason: str) -> SupervisorDecision:
        return SupervisorDecision(
            state=self._state,
            actuator=ActuatorDecision(
                mode=ActuatorMode.OFF,
                heating_permitted=False,
                cooling_permitted=False,
                reason=reason,
            ),
            reason=reason,
        )

    def _revoke(self) -> None:
        self._authority.revoke()
        self._token = None
        self._controller.inhibit()

    def _fault(self, reason: str) -> SupervisorDecision:
        self._revoke()
        self._state = SupervisorState.FAULT
        self._fault_reason = reason
        return self._off(reason)

    def _watchdog_expired(self, now_s: float) -> bool:
        if self._last_heartbeat_s is None:
            return True

        return (
            now_s - self._last_heartbeat_s
            > self._watchdog_timeout_s
        )

    def activate(self, *, now_s: float) -> SupervisorDecision:
        if self._state == SupervisorState.FAULT:
            return self._off("fault clearance required")

        if self._state == SupervisorState.ACTIVE:
            return self._fault("activation attempted while active")

        if not self._accept_time(now_s):
            return self._fault("invalid or regressing monotonic time")

        self._revoke()
        self._token = self._authority.grant()
        self._last_heartbeat_s = float(now_s)
        self._last_measurement_s = None
        self._state = SupervisorState.ACTIVE

        return self._off("supervisor activated; awaiting measurement")

    def heartbeat(self, *, now_s: float) -> SupervisorDecision:
        if self._state != SupervisorState.ACTIVE:
            return self._off("supervisor not active")

        if not self._accept_time(now_s):
            return self._fault("invalid or regressing monotonic time")

        now = float(now_s)

        if self._watchdog_expired(now):
            return self._fault("supervisory watchdog expired")

        self._last_heartbeat_s = now
        return self._off("supervisory heartbeat accepted")

    def evaluate(
        self,
        *,
        measured_c: float,
        target_c: float,
        measured_at_s: float,
        now_s: float,
    ) -> SupervisorDecision:
        if self._state != SupervisorState.ACTIVE:
            return self._off("supervisor not active")

        if not self._accept_time(now_s):
            return self._fault("invalid or regressing monotonic time")

        now = float(now_s)

        if self._watchdog_expired(now):
            return self._fault("supervisory watchdog expired")

        if not self._valid_number(measured_at_s):
            return self._fault("invalid measurement timestamp")

        measured_at = float(measured_at_s)

        if measured_at > now:
            return self._fault("future-dated measurement")

        if now - measured_at > self._measurement_timeout_s:
            return self._fault("stale temperature measurement")

        if (
            self._last_measurement_s is not None
            and measured_at < self._last_measurement_s
        ):
            return self._fault("out-of-order temperature measurement")

        if not self._valid_number(measured_c):
            return self._fault("invalid temperature measurement")

        if not self._valid_number(target_c):
            return self._fault("invalid target temperature")

        self._last_measurement_s = measured_at

        control = self._controller.evaluate(
            measured_c=measured_c,
            target_c=target_c,
            enabled=True,
        )

        actuator = self._authority.evaluate(
            token=self._token,
            heating_requested=control.heating_requested,
            cooling_requested=control.cooling_requested,
        )

        if not self._authority.authorised:
            return self._fault("actuator authority rejected request")

        return SupervisorDecision(
            state=self._state,
            actuator=actuator,
            reason="supervised temperature evaluation",
        )

    def inhibit(self) -> SupervisorDecision:
        self._revoke()
        self._state = SupervisorState.INHIBITED
        self._fault_reason = None
        self._last_heartbeat_s = None
        self._last_measurement_s = None
        return self._off("supervisor inhibited")

    def fault_status(self) -> SupervisorDecision:
        """
        Report an existing latched fault without changing state.

        This operation does not clear the fault, renew the watchdog,
        grant authority, or alter monotonic timestamps.
        """
        if self._state != SupervisorState.FAULT:
            raise RuntimeError(
                "supervisor has no latched fault"
            )

        return self._off(
            self._fault_reason or "supervisory fault latched"
        )

    def clear_fault(self) -> SupervisorDecision:
        if self._state != SupervisorState.FAULT:
            return self._off("no latched fault")

        self._revoke()
        self._state = SupervisorState.INHIBITED
        self._fault_reason = None
        self._last_heartbeat_s = None
        self._last_measurement_s = None

        return self._off("fault cleared; activation required")
