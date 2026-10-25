"""Experimental dual-direction PI temperature demand controller.

Simulation-only advisory fractions. No GPIO, compressor scheduling, safety
qualification or physical actuation. All timestamps share one monotonic clock.
"""
from dataclasses import dataclass
from math import isfinite


def _finite(value):
    return type(value) in (int, float) and isfinite(value)


@dataclass(frozen=True)
class PIDecision:
    heating_demand: float
    cooling_demand: float
    predicted_c: float
    reason: str


class PITemperatureController:
    """PI with derivative-free trend lookahead and conditional anti-windup.

    Integrators accumulate error in degree-seconds and are clamped to
    prevent runaway. Only the active direction integrates. Demand is a
    continuous advisory fraction; cooling is NOT a compressor command.
    """

    def __init__(self, *, heating_band_c=5.0, cooling_band_c=5.0,
                 integral_time_s=1800.0, lookahead_s=30.0,
                 max_rate_c_per_s=0.1, neutral_band_c=0.1,
                 max_observation_gap_s=30.0):
        for name, value, allow_zero in (
            ('heating_band_c', heating_band_c, False),
            ('cooling_band_c', cooling_band_c, False),
            ('integral_time_s', integral_time_s, False),
            ('lookahead_s', lookahead_s, True),
            ('max_rate_c_per_s', max_rate_c_per_s, False),
            ('neutral_band_c', neutral_band_c, True),
            ('max_observation_gap_s', max_observation_gap_s, False),
        ):
            if not _finite(value) or value < 0 or (not allow_zero and value == 0):
                raise ValueError(f'{name} must be finite and {"nonnegative" if allow_zero else "positive"}')
        self.heating_band_c = float(heating_band_c)
        self.cooling_band_c = float(cooling_band_c)
        self.integral_time_s = float(integral_time_s)
        self.lookahead_s = float(lookahead_s)
        self.max_rate_c_per_s = float(max_rate_c_per_s)
        self.neutral_band_c = float(neutral_band_c)
        self.max_observation_gap_s = float(max_observation_gap_s)
        self.inhibit()

    def inhibit(self):
        self._last_time = None
        self._last_temp = None
        self._last_target = None
        self._heat_integral = 0.0
        self._cool_integral = 0.0
        return PIDecision(0.0, 0.0, float('nan'), 'inhibited')

    def evaluate(self, *, measured_c, target_c, observed_at_s, enabled=False):
        if enabled is not True or not all(map(_finite, (measured_c, target_c, observed_at_s))):
            return self.inhibit()
        measured, target, now = float(measured_c), float(target_c), float(observed_at_s)
        dt = 0.0
        rate = 0.0
        if self._last_time is not None:
            dt = now - self._last_time
            if dt <= 0 or dt > self.max_observation_gap_s:
                return self.inhibit()
            if target == self._last_target:
                rate = (measured - self._last_temp) / dt
                rate = max(-self.max_rate_c_per_s, min(self.max_rate_c_per_s, rate))
            else:
                self._heat_integral = 0.0
                self._cool_integral = 0.0
                dt = 0.0
        # Predict signed temperature trend: anticipate both heating and cooling inertia.
        predicted = measured + rate * self.lookahead_s
        error = target - predicted
        if abs(error) <= self.neutral_band_c:
            error = 0.0
        if error > 0:
            self._cool_integral = 0.0
            kp = 1.0 / self.heating_band_c
            old = self._heat_integral
            proposed = min(self.integral_time_s, old + error * dt)
            raw = kp * (error + proposed / self.integral_time_s)
            # Freeze integral when already saturated high; allow unwinding.
            if raw > 1.0 and proposed > old:
                proposed = old
            self._heat_integral = proposed
            heat = min(1.0, max(0.0, kp * (error + proposed / self.integral_time_s)))
            cool = 0.0
        elif error < 0:
            self._heat_integral = 0.0
            magnitude = -error
            kp = 1.0 / self.cooling_band_c
            old = self._cool_integral
            proposed = min(self.integral_time_s, old + magnitude * dt)
            raw = kp * (magnitude + proposed / self.integral_time_s)
            if raw > 1.0 and proposed > old:
                proposed = old
            self._cool_integral = proposed
            cool = min(1.0, max(0.0, kp * (magnitude + proposed / self.integral_time_s)))
            heat = 0.0
        else:
            # Preserve integral bias within the neutral zone; no actuation there.
            heat = cool = 0.0
        self._last_time, self._last_temp, self._last_target = now, measured, target
        return PIDecision(heat, cool, predicted, 'evaluated')
