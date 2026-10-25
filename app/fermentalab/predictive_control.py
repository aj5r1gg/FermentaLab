"""Experimental finite-horizon thermal guard. SIMULATION ONLY; never drives GPIO."""
from dataclasses import dataclass
from math import isfinite
from fermentalab.thermal_model import ThermalParameters
from fermentalab.precision_pi_v39 import PrecisionPIv39


def finite(x):
    return type(x) in (int, float) and isfinite(x)


@dataclass(frozen=True)
class PredictiveDecision:
    heating_demand: float
    cooling_demand: float
    predicted_c: float
    reason: str


class PredictiveController:
    """PI baseline plus a simple finite-horizon candidate heating guard.

    Forecasts constant heating choices with an explicit 3-node Euler model.
    The guard only limits heating when forecast food overshoot is likely;
    cooling is inherited unchanged from PI. Parameters are ASSUMED, not fitted.
    """
    def __init__(self, *, parameters=None, horizon_s=900, step_s=5,
                 ambient_c=25.0, margin_c=0.05):
        self.parameters = parameters or ThermalParameters()
        if not isinstance(self.parameters, ThermalParameters):
            raise TypeError('parameters must be ThermalParameters')
        if type(horizon_s) is not int or not 60 <= horizon_s <= 3600:
            raise ValueError('horizon_s outside [60,3600]')
        if type(step_s) is not int or step_s not in (1, 2, 5) or horizon_s % step_s:
            raise ValueError('step_s must divide horizon_s and be 1,2,5')
        if not finite(ambient_c) or not finite(margin_c) or not 0 <= margin_c <= 1:
            raise ValueError('invalid ambient or margin')
        self.horizon_s, self.step_s = horizon_s, step_s
        self.ambient_c, self.margin_c = float(ambient_c), float(margin_c)
        self.base = PrecisionPIv39()
        self._last_guard_time = None
        self._last_guard_cap = 1.0

    def inhibit(self):
        d = self.base.inhibit()
        self._last_guard_time = None
        self._last_guard_cap = 1.0
        return PredictiveDecision(0, 0, d.predicted_c, 'inhibited')

    def forecast(self, *, chamber_c, vessel_c, food_c, heating_demand):
        if not all(finite(x) for x in (chamber_c, vessel_c, food_c, heating_demand)):
            raise ValueError('forecast inputs must be finite')
        if not 0 <= heating_demand <= 1:
            raise ValueError('heating demand outside [0,1]')
        p = self.parameters
        a, v, f = float(chamber_c), float(vessel_c), float(food_c)
        maximum = f
        dt = self.step_s
        for _ in range(self.horizon_s // dt):
            q_av = p.chamber_vessel_conductance_w_per_c * (a-v)
            q_vf = p.vessel_food_conductance_w_per_c * (v-f)
            na = a + dt * (p.ambient_conductance_w_per_c*(self.ambient_c-a) - q_av + p.heater_power_w*heating_demand)/p.chamber_capacity_j_per_c
            nv = v + dt * (q_av-q_vf)/p.vessel_capacity_j_per_c
            nf = f + dt * q_vf/p.food_capacity_j_per_c
            a, v, f = na, nv, nf
            maximum = max(maximum, f)
        return f, maximum

    def evaluate(self, *, measured_c, target_c, observed_at_s, enabled=False,
                 vessel_c=None, chamber_c=None):
        d = self.base.evaluate(measured_c=measured_c, target_c=target_c,
                               observed_at_s=observed_at_s, enabled=enabled,
                               vessel_c=vessel_c, chamber_c=chamber_c)
        if d.reason != 'evaluated':
            return PredictiveDecision(0, 0, d.predicted_c, d.reason)
        if vessel_c is None or chamber_c is None or d.heating_demand <= 0:
            return PredictiveDecision(d.heating_demand, d.cooling_demand, d.predicted_c, 'baseline')
        # Evaluate discrete candidates; select highest permissible heating fraction.
        # Only apply guard near target: far from target, PI remains authoritative.
        if measured_c < target_c - 3.0:
            self._last_guard_time = None
            self._last_guard_cap = 1.0
            return PredictiveDecision(d.heating_demand, 0, d.predicted_c, 'warmup')
        if (self._last_guard_time is not None and
                observed_at_s - self._last_guard_time < 30):
            return PredictiveDecision(min(d.heating_demand, self._last_guard_cap),
                                      0, d.predicted_c, 'guarded-cached')
        candidates = [k / 10 for k in range(11)]
        chosen = 0.0
        for candidate in candidates:
            _, maximum = self.forecast(chamber_c=chamber_c, vessel_c=vessel_c,
                                       food_c=measured_c, heating_demand=candidate)
            if maximum <= target_c + self.margin_c:
                chosen = candidate
        self._last_guard_time = observed_at_s
        self._last_guard_cap = chosen
        return PredictiveDecision(min(d.heating_demand, chosen), 0, d.predicted_c, 'guarded')
