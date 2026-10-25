"""Six-hour simulated comparison; no actuator authority or hardware validation."""
from dataclasses import replace
from fermentalab.thermal_model import ThermalModel, ThermalParameters
from fermentalab.precision_pi_v39 import PrecisionPIv39
from fermentalab.predictive_control import PredictiveController


def simulate(mass, *, predictive=False, duration_h=6, model_mass=None):
    if type(mass) not in (int, float) or mass <= 0:
        raise ValueError('mass must be positive')
    if type(duration_h) is not int or not 1 <= duration_h <= 24:
        raise ValueError('duration_h outside [1,24]')
    p = replace(ThermalParameters(), food_capacity_j_per_c=12000 * mass)
    plant = ThermalModel(parameters=p, initial_c=25.0)
    assumed_mass = mass if model_mass is None else model_mass
    assumed = replace(ThermalParameters(), food_capacity_j_per_c=12000 * assumed_mass)
    ctrl = PredictiveController(parameters=assumed) if predictive else PrecisionPIv39()
    total_error = in_band = 0
    maximum = float('-inf')
    first = None
    for t in range(duration_h * 3600):
        s = plant.state
        d = ctrl.evaluate(measured_c=s.food_c, target_c=42.0,
                          observed_at_s=float(t), enabled=True,
                          vessel_c=s.vessel_c, chamber_c=s.chamber_c)
        s = plant.step(dt_s=1.0, ambient_c=25.0,
                       heating_demand=d.heating_demand, cooling_demand=d.cooling_demand)
        maximum = max(maximum, s.food_c)
        err = abs(s.food_c - 42)
        if first is None and err <= 0.2:
            first = (t+1)/3600
        if t >= (duration_h-1)*3600:
            total_error += err
            in_band += err <= 0.2
    return dict(final_c=s.food_c, mae_c=total_error/3600,
                in_band_pct=in_band/36, overshoot_c=max(0, maximum-42),
                heat_wh=s.heater_energy_j/3600, first_band_h=first)


def main():
    print('STEP 42 — experimental finite-horizon heating guard; unvalidated simulation')
    print('mass model ctrl  final C  MAE C  in-band%  overshoot C  heat Wh  first-band h')
    for mass in (1.0, 1.5, 2.0, 3.0):
        for predictive, label in ((False, 'v39'), (True, 'v42')):
            r = simulate(mass, predictive=predictive)
            first = 'none' if r['first_band_h'] is None else f'{r["first_band_h"]:.2f}'
            print(f'{mass:4.1f} {mass:4.1f} {label:4} {r["final_c"]:8.3f} {r["mae_c"]:6.3f} '
                  f'{r["in_band_pct"]:8.1f} {r["overshoot_c"]:12.3f} {r["heat_wh"]:8.1f} {first:>12}')
    for model_mass in (1.0, 1.5, 3.0):
        r = simulate(2.0, predictive=True, model_mass=model_mass)
        print(f'model mismatch: actual=2.0 assumed={model_mass:.1f} MAE={r["mae_c"]:.3f} '
              f'overshoot={r["overshoot_c"]:.3f} first-band={r["first_band_h"]}')


if __name__ == '__main__':
    main()
