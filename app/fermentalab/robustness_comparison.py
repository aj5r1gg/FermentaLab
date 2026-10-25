"""Step 43: reproducible plant/model mismatch matrix; simulation only.

No GPIO, no physical compressor timing, no claims of hardware precision.
"""
from dataclasses import replace
from fermentalab.thermal_model import ThermalModel, ThermalParameters
from fermentalab.precision_pi_v39 import PrecisionPIv39
from fermentalab.predictive_control import PredictiveController

BASE = ThermalParameters()

SCENARIOS = (
    ('standard', 1.0, 25.0, 42.0, 25.0, {}, {}, None),
    ('large batch', 2.0, 25.0, 42.0, 25.0, {}, {}, None),
    ('hot ambient', 1.0, 42.0, 30.0, 42.0, {}, {}, None),
    ('weak heater', 1.0, 25.0, 42.0, 25.0, {'heater_power_w': 48.0}, {}, None),
    ('door disturbance', 1.0, 25.0, 42.0, 25.0, {}, {}, (4 * 3600, 240, -7.0)),
    ('low chamber-vessel G', 2.0, 25.0, 42.0, 25.0, {'chamber_vessel_conductance_w_per_c': 2.5}, {}, None),
    ('high chamber-vessel G', 2.0, 25.0, 42.0, 25.0, {'chamber_vessel_conductance_w_per_c': 10.0}, {}, None),
    ('low vessel-food G', 2.0, 25.0, 42.0, 25.0, {'vessel_food_conductance_w_per_c': 4.0}, {}, None),
    ('high vessel-food G', 2.0, 25.0, 42.0, 25.0, {'vessel_food_conductance_w_per_c': 16.0}, {}, None),
    ('low ambient loss', 2.0, 25.0, 42.0, 25.0, {'ambient_conductance_w_per_c': 0.75}, {}, None),
    ('high ambient loss', 2.0, 25.0, 42.0, 25.0, {'ambient_conductance_w_per_c': 3.0}, {}, None),
    ('combined mismatch', 2.0, 25.0, 42.0, 25.0,
     {'chamber_vessel_conductance_w_per_c': 2.5,
      'vessel_food_conductance_w_per_c': 4.0,
      'ambient_conductance_w_per_c': 3.0}, {}, None),
)


def simulate(scenario, *, predictive=False, duration_h=6):
    name, mass, ambient, target, initial, plant_changes, model_changes, disturbance = scenario
    if type(duration_h) is not int or not 2 <= duration_h <= 24:
        raise ValueError('duration_h must be an integer in [2,24]')
    plant_params = replace(BASE, food_capacity_j_per_c=BASE.food_capacity_j_per_c * mass,
                           **plant_changes)
    model_params = replace(BASE, food_capacity_j_per_c=BASE.food_capacity_j_per_c * mass,
                           **model_changes)
    plant = ThermalModel(parameters=plant_params, initial_c=initial)
    ctrl = (PredictiveController(parameters=model_params, ambient_c=ambient)
            if predictive else PrecisionPIv39())
    errors = []
    peak = float('-inf')
    first_band = None
    disturbance_max_error = 0.0
    for t in range(duration_h * 3600):
        state = plant.state
        decision = ctrl.evaluate(measured_c=state.food_c, target_c=target,
                                 observed_at_s=float(t), enabled=True,
                                 vessel_c=state.vessel_c, chamber_c=state.chamber_c)
        # Door opening is represented by a temporary ambient-air perturbation.
        # This is a crude proxy, NOT a model of actual door exchange.
        effective_ambient = ambient
        if disturbance is not None:
            start, length, delta = disturbance
            if start <= t < start + length:
                effective_ambient += delta
        state = plant.step(dt_s=1.0, ambient_c=effective_ambient,
                           heating_demand=decision.heating_demand,
                           cooling_demand=decision.cooling_demand)
        error = abs(state.food_c - target)
        peak = max(peak, state.food_c)
        if first_band is None and error <= 0.2:
            first_band = (t + 1) / 3600
        if t >= (duration_h - 1) * 3600:
            errors.append(error)
        if disturbance is not None and t >= disturbance[0]:
            disturbance_max_error = max(disturbance_max_error, error)
    return dict(name=name, final_c=state.food_c,
                mae_c=sum(errors)/len(errors),
                in_band_pct=100 * sum(e <= 0.2 for e in errors)/len(errors),
                overshoot_c=max(0.0, peak-target),
                first_band_h=first_band,
                heat_wh=state.heater_energy_j/3600,
                cool_wh=state.cooler_energy_j/3600,
                disturbance_max_error_c=disturbance_max_error)


def main():
    print('STEP 43 — robustness matrix; unvalidated plant, idealised actuators')
    print('Plant parameters differ from predictor assumptions where indicated.')
    print('scenario                 ctrl  MAE C   in-band%  overshoot  first h  heat Wh cool Wh')
    for scenario in SCENARIOS:
        for predictive, label in ((False, 'v39'), (True, 'v42')):
            r = simulate(scenario, predictive=predictive)
            first = 'none' if r['first_band_h'] is None else f'{r["first_band_h"]:.2f}'
            print(f'{r["name"]:24} {label:4} {r["mae_c"]:7.3f} {r["in_band_pct"]:9.1f} '
                  f'{r["overshoot_c"]:10.3f} {first:>8} {r["heat_wh"]:8.1f} {r["cool_wh"]:7.1f}')


if __name__ == '__main__':
    main()
