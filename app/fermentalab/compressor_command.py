"""
Simulation-only compressor command integration.

A successful command-admission decision is required before
compressor timing can permit cooling.

No GPIO, physical feedback, or independent safety authority.
"""

from dataclasses import dataclass

from fermentalab.command_admission import (
    CommandMode,
    SimulatedCommandAdmission,
)
from fermentalab.compressor_guard import CompressorGuard


@dataclass(frozen=True)
class CompressorCommandResult:
    mode: CommandMode
    reason: str
    remaining_off_s: float


def execute_compressor_command(
    *,
    admission: SimulatedCommandAdmission,
    identity,
    guard: CompressorGuard,
    heating: bool,
    cooling: bool,
    now_s: float,
) -> CompressorCommandResult:

    if not isinstance(admission, SimulatedCommandAdmission):
        raise TypeError("invalid command admission")

    if not isinstance(guard, CompressorGuard):
        raise TypeError("invalid compressor guard")

    admitted = admission.admit(
        identity=identity,
        heating=heating,
        cooling=cooling,
    )

    executed = admission.execute(
        identity=identity,
        decision=admitted,
    )

    # Only an accepted, executed COOLING command is eligible
    # to request compressor operation.
    cooling_authorised = (
        executed.accepted
        and executed.mode is CommandMode.COOLING
    )

    try:
        timing = guard.evaluate(
            cooling_requested=cooling_authorised,
            now_s=now_s,
        )
    except (ValueError, TypeError):
        # Invalid timing never produces an ON command.
        return CompressorCommandResult(
            mode=CommandMode.OFF,
            reason="invalid compressor timing",
            remaining_off_s=guard.minimum_off_s,
        )

    if not executed.accepted:
        return CompressorCommandResult(
            mode=CommandMode.OFF,
            reason="command admission rejected",
            remaining_off_s=timing.remaining_off_s,
        )

    if executed.mode is CommandMode.HEATING:
        return CompressorCommandResult(
            mode=CommandMode.HEATING,
            reason="heating command admitted",
            remaining_off_s=timing.remaining_off_s,
        )

    if executed.mode is CommandMode.COOLING:
        if not timing.cooling_permitted:
            return CompressorCommandResult(
                mode=CommandMode.OFF,
                reason=timing.reason,
                remaining_off_s=timing.remaining_off_s,
            )

        return CompressorCommandResult(
            mode=CommandMode.COOLING,
            reason="cooling admitted and timing satisfied",
            remaining_off_s=0.0,
        )

    return CompressorCommandResult(
        mode=CommandMode.OFF,
        reason="off command",
        remaining_off_s=timing.remaining_off_s,
    )
