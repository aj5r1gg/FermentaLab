"""
Compressor restart protection.

Software-only timing guard. This module does not operate GPIO,
switch relays, or provide independent physical safety protection.

The minimum OFF interval is configured by the caller and must
be derived from the selected compressor's requirements.
"""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class CompressorDecision:
    cooling_permitted: bool
    reason: str
    remaining_off_s: float


class CompressorGuard:
    def __init__(self, *, minimum_off_s: float):
        if (
            isinstance(minimum_off_s, bool)
            or not isinstance(minimum_off_s, (int, float))
            or not isfinite(minimum_off_s)
            or minimum_off_s <= 0
        ):
            raise ValueError(
                "minimum_off_s must be positive and finite"
            )

        self.minimum_off_s = float(minimum_off_s)
        self._last_now_s = None
        self._stopped_at_s = None
        self._running = False
        self._startup_at_s = None
        self._faulted = False

    @property
    def used(self) -> bool:
        return self._last_now_s is not None or self._faulted

    @property
    def faulted(self) -> bool:
        return self._faulted

    @property
    def running(self) -> bool:
        return self._running

    def evaluate(
        self,
        *,
        cooling_requested: bool,
        now_s: float,
    ) -> CompressorDecision:
        if type(cooling_requested) is not bool:
            raise TypeError("cooling_requested must be bool")

        if (
            isinstance(now_s, bool)
            or not isinstance(now_s, (int, float))
            or not isfinite(now_s)
        ):
            raise ValueError("now_s must be finite")

        if self._faulted:
            return CompressorDecision(
                cooling_permitted=False,
                reason="compressor timing fault latched",
                remaining_off_s=self.minimum_off_s,
            )

        now = float(now_s)

        if (
            self._last_now_s is not None
            and now < self._last_now_s
        ):
            self._running = False
            self._faulted = True
            raise ValueError("monotonic clock regression")

        self._last_now_s = now

        if self._startup_at_s is None:
            self._startup_at_s = now

        if not cooling_requested:
            if self._running:
                self._running = False
                self._stopped_at_s = now

            return CompressorDecision(
                cooling_permitted=False,
                reason="cooling not requested",
                remaining_off_s=0.0,
            )

        if self._running:
            return CompressorDecision(
                cooling_permitted=True,
                reason="cooling already active",
                remaining_off_s=0.0,
            )

        reference = (
            self._stopped_at_s
            if self._stopped_at_s is not None
            else self._startup_at_s
        )

        elapsed = now - reference
        remaining = max(0.0, self.minimum_off_s - elapsed)

        if remaining > 0:
            return CompressorDecision(
                cooling_permitted=False,
                reason="minimum OFF interval active",
                remaining_off_s=remaining,
            )

        self._running = True

        return CompressorDecision(
            cooling_permitted=True,
            reason="minimum OFF interval satisfied",
            remaining_off_s=0.0,
        )
