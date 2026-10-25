"""Step 40: inspect v39 thermal-mass sensitivity without changing control code.

Illustrative simulation only; not a physical plant or safety qualification.
"""
from dataclasses import dataclass, replace
from math import isfinite
from fermentalab.precision_pi_v39 import PrecisionPIv39
from fermentalab.thermal_model import ThermalModel, ThermalParameters


@dataclass(frozen=True)
class MassResult:
    multiplier: float
    duration_h: int
    final_food_c: float
    last_hour_mae_c: float
    last_hour_in_band_pct: float
    max_overshoot_c: float
    heater_wh: float
    first_band_entry_h: float | None
    samples: tuple


def diagnose_mass(multiplier, *, duration_h=9, target_c=42.0, ambient_c=25.0,
                  sample_interval_s=1800):
    if type(multiplier) not in (int, float) or not isfinite(multiplier) or multiplier <= 0:
        raise ValueError('multiplier must be positive and finite')
    if type(duration_h) is not int or duration_h < 1 or duration_h > 48:
        raise ValueError('duration_h must be integer in [1, 48]')
    if type(sample_interval_s) is not int or sample_interval_s < 1:
        raise ValueError('sample_interval_s must be a positive integer')
    base = ThermalParameters()
    params = replace(base, food_capacity_j_per_c=base.food_capacity_j_per_c * multiplier)
    plant = ThermalModel(parameters=params, initial_c=25.0)
    controller = PrecisionPIv39()
    tail_error_sum = tail_in_band = 0
    max_food = float('-inf')
    first_entry = None
    samples = []
    duration_s = duration_h * 3600
    for second in range(duration_s):
        before = plant.state
        decision = controller.evaluate(measured_c=before.food_c, target_c=target_c,
                                       observed_at_s=float(second), enabled=True,
                                       vessel_c=before.vessel_c, chamber_c=before.chamber_c)
        after = plant.step(dt_s=1.0, ambient_c=ambient_c,
                           heating_demand=decision.heating_demand,
                           cooling_demand=decision.cooling_demand)
        max_food = max(max_food, after.food_c)
        err = abs(after.food_c - target_c)
        if first_entry is None and err <= 0.2:
            first_entry = (second + 1) / 3600
        if second >= duration_s - 3600:
            tail_error_sum += err
            tail_in_band += err <= 0.2
        if (second + 1) % sample_interval_s == 0 or second == duration_s - 1:
            samples.append((after.elapsed_s / 3600, after.food_c, after.vessel_c,
                            after.chamber_c, decision.predicted_c,
                            decision.heating_demand, decision.cooling_demand,
                            controller._integral_demand))
    return MassResult(float(multiplier), duration_h, plant.state.food_c,
                      tail_error_sum / 3600, 100 * tail_in_band / 3600,
                      max(0.0, max_food - max(25.0, target_c)),
                      plant.state.heater_energy_j / 3600, first_entry, tuple(samples))


def main():
    print('STEP 40 — mass sensitivity; simulation only, unvalidated model.')
    print('Batch mass changes only food heat capacity, not conductance or microbial heat.')
    print('mass  hours  final C  MAE C  in-band %  overshoot C  heat Wh  first band h')
    for mass in (1.0, 1.5, 2.0, 3.0):
        for hours in (6, 9, 12):
            r = diagnose_mass(mass, duration_h=hours, sample_interval_s=3600)
            entry = 'none' if r.first_band_entry_h is None else f'{r.first_band_entry_h:.2f}'
            print(f'{mass:4.1f}  {hours:5d}  {r.final_food_c:7.3f}  '
                  f'{r.last_hour_mae_c:5.3f}  {r.last_hour_in_band_pct:9.1f}  '
                  f'{r.max_overshoot_c:11.3f}  {r.heater_wh:7.1f}  {entry:>12}')
    print('\nDouble-mass trace, six hours (hour, food, vessel, chamber, predicted, heat%, integral):')
    r = diagnose_mass(2.0, duration_h=6, sample_interval_s=3600)
    for hour, food, vessel, chamber, predicted, heat, cool, integral in r.samples:
        print(f'{hour:4.0f}  {food:7.3f}  {vessel:7.3f}  {chamber:7.3f}  '
              f'{predicted:9.3f}  {heat*100:6.1f}  {integral:8.4f}')


if __name__ == '__main__':
    main()
