"""Experimental simulation-only fine temperature demand controller.

Produces advisory demand fractions, not physical switching instructions.
Not a replacement for the normative hysteresis controller or safety layer.
"""
from dataclasses import dataclass
from math import isfinite


def _finite(value):
    return type(value) in (int, float) and isfinite(value)


@dataclass(frozen=True)
class FineTemperatureDecision:
    heating_demand: float
    cooling_requested: bool
    predicted_c: float
    reason: str


class FineTemperatureController:
    """Proportional heating with a bounded linear trend look-ahead.

    Requires monotonically increasing observation timestamps. A new target
    discards the previous trend; inhibition clears all temporal state.
    No integral action is used until a thermal plant can be characterised.
    """

    def __init__(self, *, heating_band_c=5.0, lookahead_s=30.0,
                 cooling_deadband_c=0.5, max_rate_c_per_s=0.1):
        for name, value, allow_zero in (
            ('heating_band_c', heating_band_c, False),
            ('lookahead_s', lookahead_s, True),
            ('cooling_deadband_c', cooling_deadband_c, False),
            ('max_rate_c_per_s', max_rate_c_per_s, False),
        ):
            if not _finite(value) or value < 0 or (not allow_zero and value == 0):
                raise ValueError(f'{name} must be a valid finite value')
        self.heating_band_c = float(heating_band_c)
        self.lookahead_s = float(lookahead_s)
        self.cooling_deadband_c = float(cooling_deadband_c)
        self.max_rate_c_per_s = float(max_rate_c_per_s)
        self.inhibit()

    def inhibit(self):
        self._last_time = None
        self._last_temp = None
        self._last_target = None
        return FineTemperatureDecision(0.0, False, float('nan'), 'inhibited')

    def evaluate(self, *, measured_c, target_c, observed_at_s, enabled=False):
        if enabled is not True:
            return self.inhibit()
        if not all(map(_finite, (measured_c, target_c, observed_at_s))):
            return self.inhibit()
        measured = float(measured_c)
        target = float(target_c)
        timestamp = float(observed_at_s)
        if self._last_time is not None and timestamp <= self._last_time:
            return self.inhibit()
        rate = 0.0
        if self._last_time is not None and target == self._last_target:
            rate = (measured - self._last_temp) / (timestamp - self._last_time)
            rate = max(-self.max_rate_c_per_s, min(self.max_rate_c_per_s, rate))
        predicted = measured + max(0.0, rate) * self.lookahead_s
        self._last_time = timestamp
        self._last_temp = measured
        self._last_target = target
        error = target - predicted
        heat = max(0.0, min(1.0, error / self.heating_band_c))
        # Cooling is advisory only: compressor scheduling is separate.
        cool = measured >= target + self.cooling_deadband_c and heat == 0.0
        return FineTemperatureDecision(heat, cool, predicted, 'evaluated')
