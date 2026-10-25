"""Compare v39 and inertia-aware controller across thermal masses; simulation only."""
from dataclasses import replace
from fermentalab.thermal_model import ThermalModel, ThermalParameters
from fermentalab.precision_pi_v39 import PrecisionPIv39
from fermentalab.inertia_control import InertiaAwareController


def simulate(mass, *, adaptive=False, duration_h=6, options=None):
    if type(mass) not in (int, float) or mass <= 0:
        raise ValueError('mass must be positive')
    if type(duration_h) is not int or not 1 <= duration_h <= 24:
        raise ValueError('duration_h must be in [1, 24]')
    p = ThermalParameters()
    p = replace(p, food_capacity_j_per_c=p.food_capacity_j_per_c * mass)
    plant = ThermalModel(parameters=p, initial_c=25.0)
    controller = (InertiaAwareController(food_capacity_multiplier=mass, **(options or {}))
                  if adaptive else PrecisionPIv39())
    tail_sum = tail_band = 0
    maximum = float('-inf')
    first_entry = None
    for t in range(duration_h * 3600):
        s = plant.state
        d = controller.evaluate(measured_c=s.food_c, target_c=42.0,
                                observed_at_s=float(t), enabled=True,
                                vessel_c=s.vessel_c, chamber_c=s.chamber_c)
        s = plant.step(dt_s=1.0, ambient_c=25.0,
                       heating_demand=d.heating_demand, cooling_demand=d.cooling_demand)
        maximum = max(maximum, s.food_c)
        error = abs(s.food_c - 42.0)
        if first_entry is None and error <= 0.2:
            first_entry = (t + 1) / 3600
        if t >= (duration_h - 1) * 3600:
            tail_sum += error
            tail_band += error <= 0.2
    return dict(final_c=s.food_c, mae_c=tail_sum / 3600,
                in_band_pct=100 * tail_band / 3600,
                overshoot_c=max(0.0, maximum - 42.0),
                heat_wh=s.heater_energy_j / 3600,
                first_band_h=first_entry)


def main():
    print('STEP 41: simulation-only inertia experiment; no hardware authority')
    print('mass  ctrl  final C  MAE C  in-band%  overshoot C  heat Wh  first-band h')
    for mass in (1.0, 1.5, 2.0, 3.0):
        for adaptive, label in ((False, 'v39'), (True, 'v41')):
            r = simulate(mass, adaptive=adaptive)
            first = 'none' if r['first_band_h'] is None else f'{r["first_band_h"]:.2f}'
            print(f'{mass:4.1f}  {label:4}  {r["final_c"]:7.3f}  {r["mae_c"]:5.3f}  '
                  f'{r["in_band_pct"]:7.1f}  {r["overshoot_c"]:11.3f}  '
                  f'{r["heat_wh"]:7.1f}  {first:>12}')


if __name__ == '__main__':
    main()
