"""
FermentaLab simulation-only actuator command admission.

This component provides in-memory ownership and session fencing.

It does not provide:
- cross-process hardware ownership;
- independent watchdog permission;
- durable authority reconciliation;
- GPIO or physical actuator control.

ON admission is disabled until explicitly enabled.
"""

from dataclasses import dataclass
from enum import Enum
from secrets import token_hex
from time import monotonic_ns

from fermentalab.hardware_owner import HardwareOwner


class CommandMode(Enum):
    OFF = "off"
    HEATING = "heating"
    COOLING = "cooling"


@dataclass(frozen=True)
class CommandIdentity:
    controller_epoch: str
    ownership_generation: str
    inhibition_generation: str
    execution_session_id: str


@dataclass(frozen=True)
class CommandDecision:
    accepted: bool
    mode: CommandMode
    reason: str


class SimulatedCommandAdmission:
    """In-memory simulated command-admission boundary."""

    def __init__(
        self, *, clock_ns=None, hardware_owner=None
    ):
        if (
            hardware_owner is not None
            and not isinstance(hardware_owner, HardwareOwner)
        ):
            raise TypeError(
                'hardware_owner must be a HardwareOwner'
            )
        if clock_ns is not None and not callable(clock_ns):
            raise TypeError("clock_ns must be callable")

        self._clock_ns = (
            monotonic_ns if clock_ns is None else clock_ns
        )
        self._identity = None
        self._enabled = False
        self._pending_decisions = {}
        self._command_sequence = 0
        self._hardware_owner = hardware_owner

    def _ownership_valid(self):
        if self._hardware_owner is None:
            return True

        if self._hardware_owner.valid():
            return True

        # Ownership failure invalidates the entire command
        # session, including previously admitted ON commands.
        self.revoke()
        return False

    @property
    def enabled(self):
        return self._enabled

    def is_active_identity(self, identity):
        # Object identity is intentional.
        # Reconstructed or superseded identities are invalid.
        return (
            identity is not None
            and identity is self._identity
        )

    def acquire(self, *, execution_session_id):
        if (
            not isinstance(execution_session_id, str)
            or not execution_session_id
        ):
            raise ValueError(
                "execution_session_id must be non-empty"
            )

        if self._identity is not None:
            raise RuntimeError(
                "ownership already acquired"
            )

        identity = CommandIdentity(
            controller_epoch=token_hex(16),
            ownership_generation=token_hex(16),
            inhibition_generation=token_hex(16),
            execution_session_id=execution_session_id,
        )

        self._identity = identity
        self._enabled = False
        self._pending_decisions.clear()
        self._command_sequence = 0

        return identity

    def enable(self, identity):
        if identity is None or identity is not self._identity:
            raise RuntimeError(
                "invalid ownership identity"
            )

        if not self._ownership_valid():
            raise RuntimeError(
                'hardware ownership unavailable'
            )

        self._enabled = True

    def inhibit(self, identity):
        """Withdraw ON permission without releasing ownership."""

        if identity is None or identity is not self._identity:
            raise RuntimeError("invalid ownership identity")

        self._enabled = False
        self._pending_decisions.clear()

        replacement = CommandIdentity(
            controller_epoch=identity.controller_epoch,
            ownership_generation=identity.ownership_generation,
            inhibition_generation=token_hex(16),
            execution_session_id=identity.execution_session_id,
        )

        self._identity = replacement
        return replacement

    def revoke(self):
        self._enabled = False
        self._identity = None
        self._pending_decisions.clear()

        return CommandDecision(
            accepted=True,
            mode=CommandMode.OFF,
            reason="authority revoked",
        )

    def admit(
        self,
        *,
        identity,
        heating,
        cooling,
        validity_duration_ns=5_000_000_000,
    ):
        if type(heating) is not bool or type(cooling) is not bool:
            return CommandDecision(
                accepted=False,
                mode=CommandMode.OFF,
                reason="invalid actuator request",
            )

        if not heating and not cooling:
            # OFF is an authority-reducing ordering barrier.
            # It invalidates every pending ON admission.
            self._command_sequence += 1
            self._pending_decisions.clear()

            return CommandDecision(
                accepted=True,
                mode=CommandMode.OFF,
                reason="off permitted",
            )

        if heating and cooling:
            return CommandDecision(
                accepted=False,
                mode=CommandMode.OFF,
                reason="conflicting actuator request",
            )

        if identity is None or identity is not self._identity:
            return CommandDecision(
                accepted=False,
                mode=CommandMode.OFF,
                reason="stale ownership or execution session",
            )

        if not self._ownership_valid():
            return CommandDecision(
                accepted=False,
                mode=CommandMode.OFF,
                reason='hardware ownership unavailable',
            )

        if not self._enabled:
            return CommandDecision(
                accepted=False,
                mode=CommandMode.OFF,
                reason="actuator permission inhibited",
            )

        if (
            type(validity_duration_ns) is not int
            or not 0 < validity_duration_ns <= 5_000_000_000
        ):
            return CommandDecision(
                accepted=False,
                mode=CommandMode.OFF,
                reason="invalid command validity duration",
            )

        issued_ns = self._clock_ns()

        if type(issued_ns) is not int or issued_ns < 0:
            return CommandDecision(
                accepted=False,
                mode=CommandMode.OFF,
                reason="invalid monotonic clock reading",
            )

        decision = CommandDecision(
            accepted=True,
            mode=(
                CommandMode.HEATING
                if heating
                else CommandMode.COOLING
            ),
            reason="simulated command admitted",
        )

        # A newer ON request supersedes all pending ON requests.
        self._command_sequence += 1
        self._pending_decisions.clear()
        self._pending_decisions[id(decision)] = (
            self._command_sequence,
            decision,
            issued_ns,
            validity_duration_ns,
        )
        return decision

    def execute(self, *, identity, decision):
        """Revalidate a previously admitted simulated command."""

        rejected = CommandDecision(
            accepted=False,
            mode=CommandMode.OFF,
            reason="execution authority invalid",
        )

        if not isinstance(decision, CommandDecision):
            return rejected

        if decision.mode is CommandMode.OFF:
            return CommandDecision(
                accepted=True,
                mode=CommandMode.OFF,
                reason="off permitted",
            )

        pending = self._pending_decisions.pop(
            id(decision), None
        )

        if pending is None:
            return rejected

        (
            sequence,
            issued_decision,
            issued_ns,
            validity_duration_ns,
        ) = pending

        if issued_decision is not decision:
            return rejected

        if sequence != self._command_sequence:
            return rejected

        now_ns = self._clock_ns()

        if type(now_ns) is not int or now_ns < issued_ns:
            return rejected

        if now_ns - issued_ns >= validity_duration_ns:
            return rejected

        if identity is None or identity is not self._identity:
            return rejected

        if not self._ownership_valid():
            return rejected

        if not self._enabled:
            return rejected

        return CommandDecision(
            accepted=True,
            mode=decision.mode,
            reason="simulated command executed",
        )
