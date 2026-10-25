"""Deterministic three-node thermal plant for FermentaLab experiments.

Chamber air <-> vessel <-> food; chamber <-> ambient.
Heat inputs are fractions of rated heater and cooler power. This model
is illustrative, not identified or validated against physical hardware.
It has no GPIO, actuator authority, or safety function.
"""
from dataclasses import dataclass
from math import isfinite


def _number(value):
    return type(value) in (int, float) and isfinite(value)


def _positive(value, name, *, zero=False):
    if not _number(value) or value < 0 or (not zero and value == 0):
        raise ValueError(f"{name} must be {'nonnegative' if zero else 'positive'} and finite")
    return float(value)


@dataclass(frozen=True)
class ThermalParameters:
    # Heat capacities (J/K); conductances (W/K); rated thermal power (W).
    chamber_capacity_j_per_c: float = 2500.0
    vessel_capacity_j_per_c: float = 4000.0
    food_capacity_j_per_c: float = 12000.0
    ambient_conductance_w_per_c: float = 1.5
    chamber_vessel_conductance_w_per_c: float = 5.0
    vessel_food_conductance_w_per_c: float = 8.0
    heater_power_w: float = 80.0
    cooler_power_w: float = 100.0

    def __post_init__(self):
        for name in (
            'chamber_capacity_j_per_c', 'vessel_capacity_j_per_c',
            'food_capacity_j_per_c', 'chamber_vessel_conductance_w_per_c',
            'vessel_food_conductance_w_per_c',
        ):
            _positive(getattr(self, name), name)
        for name in ('ambient_conductance_w_per_c', 'heater_power_w', 'cooler_power_w'):
            _positive(getattr(self, name), name, zero=True)


@dataclass(frozen=True)
class ThermalState:
    chamber_c: float
    vessel_c: float
    food_c: float
    elapsed_s: float = 0.0
    heater_energy_j: float = 0.0
    cooler_energy_j: float = 0.0


class ThermalModel:
    """Explicit Euler energy-balance model with a bounded simulation step.

    Caller must select a timestep small enough for numerical stability;
    the 1-second default is appropriate for the supplied example values.
    """

    def __init__(self, *, parameters=None, initial_c=25.0):
        self.parameters = parameters if parameters is not None else ThermalParameters()
        if not isinstance(self.parameters, ThermalParameters):
            raise TypeError('parameters must be ThermalParameters')
        initial = _positive(initial_c, 'initial_c', zero=True)
        self.state = ThermalState(initial, initial, initial)

    def step(self, *, dt_s, ambient_c, heating_demand=0.0, cooling_demand=0.0):
        dt = _positive(dt_s, 'dt_s')
        if dt > 5.0:
            raise ValueError('dt_s must not exceed 5 seconds; subdivide the simulation')
        if not _number(ambient_c):
            raise ValueError('ambient_c must be finite')
        heat = _positive(heating_demand, 'heating_demand', zero=True)
        cool = _positive(cooling_demand, 'cooling_demand', zero=True)
        if heat > 1 or cool > 1:
            raise ValueError('demands must be between 0 and 1')
        if heat > 0 and cool > 0:
            raise ValueError('simultaneous heating and cooling is prohibited')

        p, s = self.parameters, self.state
        ambient_flow = p.ambient_conductance_w_per_c * (float(ambient_c) - s.chamber_c)
        chamber_vessel_flow = p.chamber_vessel_conductance_w_per_c * (s.chamber_c - s.vessel_c)
        vessel_food_flow = p.vessel_food_conductance_w_per_c * (s.vessel_c - s.food_c)
        heater_w = p.heater_power_w * heat
        cooler_w = p.cooler_power_w * cool

        self.state = ThermalState(
            chamber_c=s.chamber_c + dt * (ambient_flow - chamber_vessel_flow + heater_w - cooler_w) / p.chamber_capacity_j_per_c,
            vessel_c=s.vessel_c + dt * (chamber_vessel_flow - vessel_food_flow) / p.vessel_capacity_j_per_c,
            food_c=s.food_c + dt * vessel_food_flow / p.food_capacity_j_per_c,
            elapsed_s=s.elapsed_s + dt,
            heater_energy_j=s.heater_energy_j + heater_w * dt,
            cooler_energy_j=s.cooler_energy_j + cooler_w * dt,
        )
        return self.state
