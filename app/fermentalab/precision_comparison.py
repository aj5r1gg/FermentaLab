"""Compare original PI and experimental precision PI on the same model."""
from dataclasses import replace
from fermentalab.pi_comparison import SCENARIOS
from fermentalab.pi_temperature_control import PITemperatureController
from fermentalab.precision_temperature_control import PrecisionTemperatureController
from fermentalab.thermal_model import ThermalModel, ThermalParameters


def simulate(scenario, *, precision=False, duration_s=21600):
    if type(duration_s) is not int or duration_s < 3600:
        raise ValueError('duration_s must be an integer >= 3600')
    p = ThermalParameters()
    p = replace(p, food_capacity_j_per_c=p.food_capacity_j_per_c * scenario.food_capacity_multiplier,
                heater_power_w=p.heater_power_w * scenario.heater_power_multiplier)
    plant = ThermalModel(parameters=p, initial_c=scenario.initial_c)
    controller = PrecisionTemperatureController() if precision else PITemperatureController()
    temperatures = []
    recovery = []
    for second in range(duration_s):
        if scenario.door_open_at_s == second:
            plant.state = replace(plant.state, chamber_c=scenario.ambient_c)
        state = plant.state
        args = dict(measured_c=state.food_c, target_c=scenario.target_c,
                    observed_at_s=float(second), enabled=True)
        if precision:
            args.update(vessel_c=state.vessel_c, chamber_c=state.chamber_c)
        demand = controller.evaluate(**args)
        state = plant.step(dt_s=1, ambient_c=scenario.ambient_c,
                           heating_demand=demand.heating_demand,
                           cooling_demand=demand.cooling_demand)
        temperatures.append(state.food_c)
        if scenario.door_open_at_s is not None and second >= scenario.door_open_at_s:
            recovery.append(abs(state.food_c - scenario.target_c))
    last = temperatures[-3600:]
    # Time within tolerance in the final hour is more informative than final point alone.
    return dict(final=temperatures[-1],
                mae=sum(abs(x-scenario.target_c) for x in last)/len(last),
                in_band=sum(abs(x-scenario.target_c) <= 0.2 for x in last)/len(last)*100,
                max_above=max(0.0, max(temperatures)-max(scenario.target_c, scenario.initial_c)),
                max_below=max(0.0, min(scenario.target_c, scenario.initial_c)-min(temperatures)),
                heat_wh=plant.state.heater_energy_j/3600,
                cool_wh=plant.state.cooler_energy_j/3600,
                disturbance_max_error=max(recovery) if recovery else None)


def main():
    print('SIMULATION ONLY: unvalidated plant, idealised cooling, no compressor scheduling.')
    for scenario in SCENARIOS:
        print(f'\n{scenario.name}: target={scenario.target_c:g} C ambient={scenario.ambient_c:g} C')
        for name, precision in [('PI v36', False), ('PI v37', True)]:
            r = simulate(scenario, precision=precision)
            print(f'  {name:6} final={r["final"]:.3f} C  MAE={r["mae"]:.3f} C  '
                  f'in-band={r["in_band"]:.1f}%  overshoot={r["max_above"]:.3f} C  '
                  f'heat={r["heat_wh"]:.1f} Wh  cool={r["cool_wh"]:.1f} Wh')
            if r['disturbance_max_error'] is not None:
                print(f'         post-disturbance max error={r["disturbance_max_error"]:.3f} C')


if __name__ == '__main__':
    main()
