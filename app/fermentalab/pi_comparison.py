"""Illustrative PI-versus-baseline thermal simulations; not hardware validation."""
from dataclasses import dataclass
from fermentalab.pi_temperature_control import PITemperatureController
from fermentalab.thermal_model import ThermalModel, ThermalParameters
from fermentalab.controller_comparison import simulate


@dataclass(frozen=True)
class Scenario:
    name: str
    ambient_c: float
    target_c: float
    initial_c: float = 25.0
    food_capacity_multiplier: float = 1.0
    heater_power_multiplier: float = 1.0
    door_open_at_s: int | None = None


SCENARIOS = (
    Scenario('Incubation', 25, 42),
    Scenario('Hot ambient', 42, 30),
    Scenario('Low-temperature', 25, 22),
    Scenario('Large batch', 25, 42, food_capacity_multiplier=2.0),
    Scenario('Weak heater', 25, 42, heater_power_multiplier=0.6),
    Scenario('Door disturbance', 25, 42, door_open_at_s=10800),
)


def simulate_pi(scenario, *, duration_s=21600):
    """One-second plant simulation; door disturbance approximated as air mixing."""
    if not isinstance(scenario, Scenario):
        raise TypeError('scenario must be Scenario')
    if type(duration_s) is not int or duration_s < 3600:
        raise ValueError('duration_s must be integer >= 3600')
    base = ThermalParameters()
    parameters = ThermalParameters(
        chamber_capacity_j_per_c=base.chamber_capacity_j_per_c,
        vessel_capacity_j_per_c=base.vessel_capacity_j_per_c,
        food_capacity_j_per_c=base.food_capacity_j_per_c * scenario.food_capacity_multiplier,
        ambient_conductance_w_per_c=base.ambient_conductance_w_per_c,
        chamber_vessel_conductance_w_per_c=base.chamber_vessel_conductance_w_per_c,
        vessel_food_conductance_w_per_c=base.vessel_food_conductance_w_per_c,
        heater_power_w=base.heater_power_w * scenario.heater_power_multiplier,
        cooler_power_w=base.cooler_power_w,
    )
    plant = ThermalModel(parameters=parameters, initial_c=scenario.initial_c)
    controller = PITemperatureController()
    history = []
    for second in range(duration_s):
        if scenario.door_open_at_s is not None and second == scenario.door_open_at_s:
            # Illustrative instantaneous chamber-air mixing, not a validated door model.
            from dataclasses import replace
            plant.state = replace(plant.state, chamber_c=scenario.ambient_c)
        decision = controller.evaluate(
            measured_c=plant.state.food_c, target_c=scenario.target_c,
            observed_at_s=float(second), enabled=True,
        )
        state = plant.step(dt_s=1, ambient_c=scenario.ambient_c,
                           heating_demand=decision.heating_demand,
                           cooling_demand=decision.cooling_demand)
        history.append(state.food_c)
    tail = history[-3600:]
    return {
        'final_food_c': history[-1],
        'last_hour_mae_c': sum(abs(t-scenario.target_c) for t in tail)/len(tail),
        'post_start_overshoot_c': max(0, max(history)-max(scenario.target_c, scenario.initial_c)),
        'heater_wh': plant.state.heater_energy_j/3600,
        'cooler_wh': plant.state.cooler_energy_j/3600,
    }


def main():
    print('SIMULATION ONLY: idealised fractional cooling; no physical compressor scheduling.')
    print('Baseline comparisons only where plant parameters match original Step 35.')
    for s in SCENARIOS:
        r = simulate_pi(s)
        print(f'\n{s.name}: ambient={s.ambient_c:g} target={s.target_c:g} initial={s.initial_c:g}')
        print(f'  PI   final={r["final_food_c"]:.2f} C  last-hour MAE={r["last_hour_mae_c"]:.3f} C  '
              f'post-start overshoot={r["post_start_overshoot_c"]:.3f} C  '
              f'heat={r["heater_wh"]:.1f} Wh cool={r["cooler_wh"]:.1f} Wh')
        if s.food_capacity_multiplier == s.heater_power_multiplier == 1 and s.door_open_at_s is None:
            for method in ('hysteresis', 'fine'):
                b = simulate(controller=method, ambient_c=s.ambient_c,
                             target_c=s.target_c, initial_c=s.initial_c)
                print(f'  {method:10} final={b.final_food_c:.2f} C  '
                      f'last-hour MAE={b.mean_last_hour_abs_error_c:.3f} C  '
                      f'heat={b.heater_energy_wh:.1f} Wh cool={b.cooler_energy_wh:.1f} Wh')


if __name__ == '__main__':
    main()
