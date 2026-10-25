"""Six-scenario v36 versus v39 comparison; deterministic illustrative model."""
from dataclasses import replace
from fermentalab.pi_comparison import SCENARIOS, simulate_pi
from fermentalab.precision_pi_v39 import PrecisionPIv39
from fermentalab.thermal_model import ThermalModel, ThermalParameters


def simulate_v39(scenario, *, duration_s=21600, controller_options=None):
    if type(duration_s) is not int or duration_s < 3600:
        raise ValueError('duration_s must be integer >= 3600')
    base = ThermalParameters()
    p = replace(base, food_capacity_j_per_c=base.food_capacity_j_per_c * scenario.food_capacity_multiplier,
                heater_power_w=base.heater_power_w * scenario.heater_power_multiplier)
    plant = ThermalModel(parameters=p, initial_c=scenario.initial_c)
    controller = PrecisionPIv39(**(controller_options or {}))
    food_history = []
    disturbance_errors = []
    for second in range(duration_s):
        if scenario.door_open_at_s == second:
            plant.state = replace(plant.state, chamber_c=scenario.ambient_c)
        state = plant.state
        d = controller.evaluate(measured_c=state.food_c, target_c=scenario.target_c,
                                observed_at_s=float(second), enabled=True,
                                vessel_c=state.vessel_c, chamber_c=state.chamber_c)
        state = plant.step(dt_s=1.0, ambient_c=scenario.ambient_c,
                           heating_demand=d.heating_demand, cooling_demand=d.cooling_demand)
        food_history.append(state.food_c)
        if scenario.door_open_at_s is not None and second >= scenario.door_open_at_s:
            disturbance_errors.append(abs(state.food_c-scenario.target_c))
    tail = food_history[-3600:]
    return dict(final_food_c=food_history[-1],
                last_hour_mae_c=sum(abs(t-scenario.target_c) for t in tail)/len(tail),
                last_hour_in_band_pct=100*sum(abs(t-scenario.target_c)<=0.2 for t in tail)/len(tail),
                post_start_overshoot_c=max(0.0, max(food_history)-max(scenario.initial_c,scenario.target_c)),
                heater_wh=plant.state.heater_energy_j/3600,
                cooler_wh=plant.state.cooler_energy_j/3600,
                disturbance_max_error_c=max(disturbance_errors) if disturbance_errors else None)


def main():
    print('SIMULATION ONLY — unvalidated thermal plant; idealised cooling, no compressor scheduler.')
    print('Performance objective: last-hour MAE <= 0.2 C, NOT proof of +/-0.2 C containment.')
    for scenario in SCENARIOS:
        baseline = simulate_pi(scenario)
        revised = simulate_v39(scenario)
        print(f'\n{scenario.name}: target={scenario.target_c:g} C, ambient={scenario.ambient_c:g} C')
        print(f'  v36 MAE={baseline["last_hour_mae_c"]:.3f} C  final={baseline["final_food_c"]:.3f} C  '
              f'heat={baseline["heater_wh"]:.1f} Wh cool={baseline["cooler_wh"]:.1f} Wh')
        print(f'  v39 MAE={revised["last_hour_mae_c"]:.3f} C  final={revised["final_food_c"]:.3f} C  '
              f'in-band={revised["last_hour_in_band_pct"]:.1f}%  overshoot={revised["post_start_overshoot_c"]:.3f} C  '
              f'heat={revised["heater_wh"]:.1f} Wh cool={revised["cooler_wh"]:.1f} Wh')
        if revised['disturbance_max_error_c'] is not None:
            print(f'  post-disturbance max error={revised["disturbance_max_error_c"]:.3f} C')


if __name__ == '__main__':
    main()
