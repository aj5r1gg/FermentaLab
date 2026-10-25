"""Simulation-only diagnostics for existing v36/v37 controllers; no actuation."""
from dataclasses import replace
from fermentalab.pi_comparison import SCENARIOS
from fermentalab.pi_temperature_control import PITemperatureController
from fermentalab.precision_temperature_control import PrecisionTemperatureController
from fermentalab.thermal_model import ThermalModel, ThermalParameters


def run_diagnostics(scenario, *, precision=False, duration_s=21600, sample_every_s=900):
    if type(duration_s) is not int or duration_s < 1:
        raise ValueError('duration_s must be a positive integer')
    if type(sample_every_s) is not int or sample_every_s < 1:
        raise ValueError('sample_every_s must be a positive integer')
    base = ThermalParameters()
    p = replace(base, food_capacity_j_per_c=base.food_capacity_j_per_c * scenario.food_capacity_multiplier,
                heater_power_w=base.heater_power_w * scenario.heater_power_multiplier)
    plant = ThermalModel(parameters=p, initial_c=scenario.initial_c)
    controller = PrecisionTemperatureController() if precision else PITemperatureController()
    samples = []
    heat_transitions = cool_transitions = 0
    last_heat = last_cool = False
    for second in range(duration_s):
        if scenario.door_open_at_s is not None and second == scenario.door_open_at_s:
            plant.state = replace(plant.state, chamber_c=scenario.ambient_c)
        before = plant.state
        kwargs = dict(measured_c=before.food_c, target_c=scenario.target_c,
                      observed_at_s=float(second), enabled=True)
        if precision:
            kwargs.update(vessel_c=before.vessel_c, chamber_c=before.chamber_c)
        decision = controller.evaluate(**kwargs)
        heating = decision.heating_demand > 0
        cooling = decision.cooling_demand > 0
        heat_transitions += heating != last_heat
        cool_transitions += cooling != last_cool
        last_heat, last_cool = heating, cooling
        after = plant.step(dt_s=1, ambient_c=scenario.ambient_c,
                           heating_demand=decision.heating_demand,
                           cooling_demand=decision.cooling_demand)
        if second == 0 or (second + 1) % sample_every_s == 0 or second == duration_s - 1:
            samples.append(dict(time_h=(second + 1) / 3600,
                                food_c=after.food_c, vessel_c=after.vessel_c,
                                chamber_c=after.chamber_c, predicted_c=decision.predicted_c,
                                heat=decision.heating_demand, cool=decision.cooling_demand,
                                heat_integral=getattr(controller, '_heat_integral', None),
                                cool_integral=getattr(controller, '_cool_integral', None)))
    delta = scenario.target_c - scenario.ambient_c
    required_w = p.ambient_conductance_w_per_c * abs(delta)
    available_w = p.heater_power_w if delta > 0 else p.cooler_power_w
    return dict(samples=samples, heat_transitions=heat_transitions,
                cool_transitions=cool_transitions, equilibrium_required_w=required_w,
                equilibrium_capacity_w=available_w,
                equilibrium_fraction=(required_w / available_w if available_w else float('inf')),
                final=plant.state)


def main():
    print('DIAGNOSTICS ONLY — illustrative model, no GPIO or compressor scheduling.')
    for scenario in SCENARIOS:
        print(f'\n{scenario.name}: target={scenario.target_c:g} C ambient={scenario.ambient_c:g} C')
        for label, precision in (('v36', False), ('v37', True)):
            result = run_diagnostics(scenario, precision=precision)
            print(f'  {label}: equilibrium demand={result["equilibrium_fraction"]:.1%} '
                  f'({result["equilibrium_required_w"]:.1f}/{result["equilibrium_capacity_w"]:.1f} W); '
                  f'heat transitions={result["heat_transitions"]}; cool transitions={result["cool_transitions"]}')
            print('   hour    food   vessel  chamber predicted   heat%   cool%  heat_integral  cool_integral')
            for row in result['samples']:
                if abs(row['time_h'] - round(row['time_h'])) < 0.001 or row['time_h'] < 0.001:
                    hi = row['heat_integral']
                    ci = row['cool_integral']
                    print(f'   {row["time_h"]:4.1f}  {row["food_c"]:6.2f}  {row["vessel_c"]:6.2f}  '
                          f'{row["chamber_c"]:7.2f}  {row["predicted_c"]:8.2f}  '
                          f'{100*row["heat"]:5.1f}  {100*row["cool"]:5.1f}  '
                          f'{hi if hi is not None else "n/a"!s:>13}  {ci if ci is not None else "n/a"!s:>13}')


if __name__ == '__main__':
    main()
