"""Simulation-only mass-aware prediction experiment; no physical actuation."""
from dataclasses import dataclass
from math import isfinite
from fermentalab.precision_pi_v39 import PrecisionPIv39


@dataclass(frozen=True)
class InertiaDecision:
    heating_demand: float
    cooling_demand: float
    predicted_c: float
    reason: str


class InertiaAwareController:
    """Scale v39's upstream prediction gains by an assumed mass multiplier.

    The multiplier is an experimental model parameter, not an automatically
    identified property. This candidate is NOT a validated improvement.
    """
    def __init__(self, *, food_capacity_multiplier=1.0,
                 vessel_gain_per_extra_mass=0.15,
                 chamber_gain_per_extra_mass=0.025):
        for name, val in (('food_capacity_multiplier', food_capacity_multiplier),
                          ('vessel_gain_per_extra_mass', vessel_gain_per_extra_mass),
                          ('chamber_gain_per_extra_mass', chamber_gain_per_extra_mass)):
            if type(val) not in (int, float) or not isfinite(val) or val < 0 or (name == 'food_capacity_multiplier' and val == 0):
                raise ValueError(f'{name} must be valid')
        extra = max(0.0, float(food_capacity_multiplier) - 1.0)
        self.base = PrecisionPIv39(
            vessel_prediction_gain=0.25 + float(vessel_gain_per_extra_mass) * extra,
            chamber_prediction_gain=0.05 + float(chamber_gain_per_extra_mass) * extra)

    def inhibit(self):
        d = self.base.inhibit()
        return InertiaDecision(d.heating_demand, d.cooling_demand, d.predicted_c, d.reason)

    def evaluate(self, *, measured_c, target_c, observed_at_s, enabled=False,
                 vessel_c=None, chamber_c=None):
        d = self.base.evaluate(measured_c=measured_c, target_c=target_c,
                               observed_at_s=observed_at_s, enabled=enabled,
                               vessel_c=vessel_c, chamber_c=chamber_c)
        return InertiaDecision(d.heating_demand, d.cooling_demand, d.predicted_c, d.reason)
