"""Deterministic comparison of FermentaLab advisory controllers.

Research-only: idealised cooling, no safety authority or physical switching.
"""
from dataclasses import dataclass
from fermentalab.temperature_control import TemperatureController
from fermentalab.fine_temperature_control import FineTemperatureController
from fermentalab.thermal_model import ThermalModel


@dataclass(frozen=True)
class ComparisonResult:
    controller: str
    ambient_c: float
    target_c: float
    final_food_c: float
    peak_food_c: float
    maximum_overshoot_c: float
    final_error_c: float
    mean_last_hour_abs_error_c: float
    heater_energy_wh: float
    cooler_energy_wh: float
    settling_time_s: float | None
    final_chamber_c: float
    final_vessel_c: float


def simulate(*, controller, ambient_c, target_c, initial_c=25.0,
             duration_s=21600, dt_s=1.0, tolerance_c=0.2):
    """Run one idealised plant simulation; settling means stays in band thereafter."""
    if controller not in ('hysteresis', 'fine'):
        raise ValueError('controller must be hysteresis or fine')
    if type(duration_s) is not int or duration_s < 3600:
        raise ValueError('duration_s must be integer >= 3600')
    if dt_s != 1.0:
        raise ValueError('comparison currently requires dt_s=1.0')
    plant = ThermalModel(initial_c=initial_c)
    control = (TemperatureController(deadband_c=0.5) if controller == 'hysteresis'
               else FineTemperatureController())
    history = []
    for second in range(duration_s):
        food = plant.state.food_c
        if controller == 'hysteresis':
            decision = control.evaluate(food, target_c, enabled=True)
            heating = float(decision.heating_requested)
            cooling = float(decision.cooling_requested)
        else:
            decision = control.evaluate(measured_c=food, target_c=target_c,
                                        observed_at_s=float(second), enabled=True)
            heating = decision.heating_demand
            cooling = float(decision.cooling_requested)
        state = plant.step(dt_s=dt_s, ambient_c=ambient_c,
                           heating_demand=heating, cooling_demand=cooling)
        history.append(state.food_c)
    errors = [abs(t - target_c) for t in history]
    settled = None
    # Last time outside tolerance determines earliest permanent settling time.
    last_outside = next((i for i in range(len(errors)-1, -1, -1)
                         if errors[i] > tolerance_c), None)
    if last_outside is None:
        settled = 0.0
    elif last_outside < len(errors) - 1:
        settled = float(last_outside + 1) * dt_s
    return ComparisonResult(
        controller=controller, ambient_c=float(ambient_c), target_c=float(target_c),
        final_food_c=plant.state.food_c, peak_food_c=max(history),
        maximum_overshoot_c=max(0.0, max(history) - target_c),
        final_error_c=plant.state.food_c-target_c,
        mean_last_hour_abs_error_c=sum(errors[-3600:])/3600,
        heater_energy_wh=plant.state.heater_energy_j/3600,
        cooler_energy_wh=plant.state.cooler_energy_j/3600,
        settling_time_s=settled,
        final_chamber_c=plant.state.chamber_c,
        final_vessel_c=plant.state.vessel_c,
    )


def main():
    scenarios = (
        ('Incubation', 25.0, 42.0),
        ('Hot ambient', 42.0, 30.0),
        ('Low-temperature', 25.0, 22.0),
    )
    print('Illustrative, unvalidated thermal model; idealised cooling.')
    for name, ambient, target in scenarios:
        print(f'\n{name}: ambient={ambient:.1f} C, target={target:.1f} C')
        for method in ('hysteresis', 'fine'):
            r = simulate(controller=method, ambient_c=ambient, target_c=target)
            settling = ('not settled' if r.settling_time_s is None
                        else f'{r.settling_time_s/3600:.2f} h')
            print(f'  {method:10} food={r.final_food_c:6.2f} C  '
                  f'overshoot={r.maximum_overshoot_c:5.2f} C  '
                  f'last-hour MAE={r.mean_last_hour_abs_error_c:5.2f} C  '
                  f'settling={settling:>11}  '
                  f'heat={r.heater_energy_wh:6.1f} Wh  '
                  f'cool={r.cooler_energy_wh:6.1f} Wh')


if __name__ == '__main__':
    main()
