"""Experimental PI with signed integral bias and optional thermal-state feed-forward.

Simulation-only demand fractions; not an actuator or compressor scheduler.
"""
from dataclasses import dataclass
from math import isfinite


def finite(x):
    return type(x) in (int, float) and isfinite(x)


@dataclass(frozen=True)
class PrecisionDecision:
    heating_demand: float
    cooling_demand: float
    predicted_c: float
    reason: str


class PrecisionTemperatureController:
    def __init__(self, *, heating_band_c=5.0, cooling_band_c=5.0,
                 integral_time_s=900.0, lookahead_s=30.0,
                 max_rate_c_per_s=0.1, max_observation_gap_s=30.0,
                 vessel_prediction_gain=0.0, chamber_prediction_gain=0.0):
        values = locals().copy()
        for name, value in values.items():
            if name == 'self':
                continue
            if not finite(value) or value < 0 or (name in (
                'heating_band_c', 'cooling_band_c', 'integral_time_s',
                'max_rate_c_per_s', 'max_observation_gap_s') and value == 0):
                raise ValueError(f'{name} must be finite and valid')
            setattr(self, name, float(value))
        self.inhibit()

    def inhibit(self):
        self._last_time = self._last_temp = self._last_target = None
        self._integral = 0.0
        return PrecisionDecision(0, 0, float('nan'), 'inhibited')

    def evaluate(self, *, measured_c, target_c, observed_at_s, enabled=False,
                 vessel_c=None, chamber_c=None):
        if enabled is not True or not all(finite(v) for v in (measured_c, target_c, observed_at_s)):
            return self.inhibit()
        if (vessel_c is not None and not finite(vessel_c)) or (chamber_c is not None and not finite(chamber_c)):
            return self.inhibit()
        now, measured, target = float(observed_at_s), float(measured_c), float(target_c)
        dt = 0.0
        rate = 0.0
        if self._last_time is not None:
            dt = now - self._last_time
            if dt <= 0 or dt > self.max_observation_gap_s:
                return self.inhibit()
            if target != self._last_target:
                self._integral = 0.0
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
        # Signed integral persists through zero error, preventing loss of bias.
        # Candidate integral is conditionally accepted when it does not deepen saturation.
        proposed = max(-self.integral_time_s, min(self.integral_time_s,
                       self._integral + error * dt))
        band = self.heating_band_c if error + proposed / self.integral_time_s >= 0 else self.cooling_band_c
        raw = (error + proposed / self.integral_time_s) / band
        if (raw > 1 and error > 0) or (raw < -1 and error < 0):
            proposed = self._integral
        self._integral = proposed
        control = error + self._integral / self.integral_time_s
        heat = max(0.0, min(1.0, control / self.heating_band_c))
        cool = max(0.0, min(1.0, -control / self.cooling_band_c))
        self._last_time, self._last_temp, self._last_target = now, measured, target
        return PrecisionDecision(heat, cool, predicted, 'evaluated')
