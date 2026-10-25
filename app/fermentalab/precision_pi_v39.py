"""Experimental signed PI demand controller; simulation ONLY, no physical authority."""
from dataclasses import dataclass
from math import isfinite


def _valid(x):
    return type(x) in (int, float) and isfinite(x)


@dataclass(frozen=True)
class PrecisionPIDecision:
    heating_demand: float
    cooling_demand: float
    predicted_c: float
    reason: str


class PrecisionPIv39:
    """PI with output-unit integral, conditional anti-windup and optional state prediction.

    Integral represents signed actuator demand, clamped to [-1, 1], not
    degree-seconds. Cooling fractions are idealised; never switch a compressor
    directly from these values.
    """
    def __init__(self, *, heating_band_c=5.0, cooling_band_c=5.0,
                 integral_time_s=5400.0, lookahead_s=30.0,
                 vessel_prediction_gain=0.25, chamber_prediction_gain=0.05,
                 max_rate_c_per_s=0.1, max_observation_gap_s=30.0):
        for name, val in locals().copy().items():
            if name == 'self':
                continue
            if not _valid(val) or val < 0 or (name in (
                'heating_band_c', 'cooling_band_c', 'integral_time_s',
                'max_rate_c_per_s', 'max_observation_gap_s') and val == 0):
                raise ValueError(f'{name} must be valid and finite')
            setattr(self, name, float(val))
        self.inhibit()

    def inhibit(self):
        self._last_time = self._last_temp = self._last_target = None
        self._integral_demand = 0.0
        return PrecisionPIDecision(0.0, 0.0, float('nan'), 'inhibited')

    def evaluate(self, *, measured_c, target_c, observed_at_s, enabled=False,
                 vessel_c=None, chamber_c=None):
        if enabled is not True or not all(_valid(x) for x in (measured_c, target_c, observed_at_s)):
            return self.inhibit()
        if (vessel_c is not None and not _valid(vessel_c)) or (chamber_c is not None and not _valid(chamber_c)):
            return self.inhibit()
        measured, target, now = float(measured_c), float(target_c), float(observed_at_s)
        dt, rate = 0.0, 0.0
        if self._last_time is not None:
            dt = now - self._last_time
            if dt <= 0 or dt > self.max_observation_gap_s:
                return self.inhibit()
            if target != self._last_target:
                self._integral_demand = 0.0
                dt = 0.0
            else:
                rate = max(-self.max_rate_c_per_s, min(self.max_rate_c_per_s,
                    (measured - self._last_temp) / dt))
        predicted = measured + rate * self.lookahead_s
        if vessel_c is not None:
            predicted += self.vessel_prediction_gain * (float(vessel_c) - measured)
        if chamber_c is not None:
            predicted += self.chamber_prediction_gain * (float(chamber_c) - measured)
        error = target - predicted
        band = self.heating_band_c if error >= 0 else self.cooling_band_c
        proportional = error / band
        proposed = max(-1.0, min(1.0, self._integral_demand + error * dt / (band * self.integral_time_s)))
        raw = proportional + proposed
        if (raw > 1 and error > 0) or (raw < -1 and error < 0):
            proposed = self._integral_demand
        self._integral_demand = proposed
        raw = proportional + self._integral_demand
        heat = min(1.0, max(0.0, raw))
        cool = min(1.0, max(0.0, -raw))
        self._last_time, self._last_temp, self._last_target = now, measured, target
        return PrecisionPIDecision(heat, cool, predicted, 'evaluated')
