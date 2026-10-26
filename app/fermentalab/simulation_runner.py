"""
FermentaLab deterministic fermentation simulation runner.

Simulation only.

Coordinates the existing fermentation runtime and illustrative
thermal model.

No GPIO, physical actuators, compressor scheduler, or independent
hardware safety mechanisms are implemented here.
"""

from dataclasses import dataclass
from math import isfinite

from fermentalab.command_admission import (
    CommandIdentity,
    CommandMode,
    SimulatedCommandAdmission,
)
from fermentalab.execution_coordinator import (
    ExecutionCoordinator,
)
from fermentalab.fermentation_runtime import (
    FermentationRuntime,
    RuntimeState,
)
from fermentalab.recipes import Recipe
from fermentalab.sensors import (
    ChamberTemperatureReading,
    SimulatedChamberTemperatureSensor,
)
from fermentalab.thermal_model import ThermalModel


@dataclass(frozen=True)
class SupplementarySensorConfig:
    sensor_id: str
    offset_c: float = 0.0

    def __post_init__(self):
        if (
            not isinstance(self.sensor_id, str)
            or not self.sensor_id.strip()
            or self.sensor_id == 'chamber-primary'
        ):
            raise ValueError('invalid supplementary sensor_id')
        if (
            type(self.offset_c) not in (int, float)
            or not isfinite(self.offset_c)
        ):
            raise ValueError('offset_c must be finite and numeric')


@dataclass(frozen=True)
class SupplementarySensorFailure:
    sensor_id: str
    error: str


@dataclass(frozen=True)
class SimulationSample:
    elapsed_s: float
    ambient_c: float
    chamber_c: float
    vessel_c: float
    food_c: float
    progress_percent: float
    heating_permitted: bool
    cooling_permitted: bool


@dataclass(frozen=True)
class SimulationObservation:
    elapsed_s: float
    stage_name: str
    target_c: float | None
    chamber_c: float
    food_c: float
    progress_percent: float
    heating_permitted: bool
    cooling_permitted: bool
    state: RuntimeState
    supplementary_readings: tuple[ChamberTemperatureReading, ...] = ()
    supplementary_failures: tuple[SupplementarySensorFailure, ...] = ()


@dataclass(frozen=True)
class SimulationResult:
    state: RuntimeState
    samples: tuple[SimulationSample, ...]
    minimum_chamber_c: float
    maximum_chamber_c: float
    heating_seconds: float
    cooling_seconds: float
    idle_seconds: float


class SimulationRunner:
    """
    Deterministic simulation coordinator.

    A simulation run starts with a fresh runtime and thermal model.

    The ambient temperature may be supplied as a constant or as a
    callable accepting elapsed simulation seconds.

    This class does not establish physical actuator authority.
    """

    def __init__(
        self,
        recipe: Recipe,
        *,
        initial_c: float = 25.0,
        step_s: float = 5.0,
    ):
        if not isinstance(recipe, Recipe):
            raise TypeError("recipe must be a Recipe")

        if (
            type(initial_c) not in (int, float)
            or not isfinite(initial_c)
            or initial_c < 0
        ):
            raise ValueError(
                "initial_c must be finite and nonnegative"
            )

        if (
            type(step_s) not in (int, float)
            or not isfinite(step_s)
            or not 0 < step_s <= 5
        ):
            raise ValueError(
                "step_s must be greater than zero and at most 5"
            )

        self.recipe = recipe
        self.initial_c = float(initial_c)
        self.step_s = float(step_s)

    def run(
        self,
        *,
        ambient_c,
        coordinator: ExecutionCoordinator | None = None,
        command_admission: SimulatedCommandAdmission | None = None,
        command_identity: CommandIdentity | None = None,
        observer=None,
        report_every_s: float = 900.0,
        supplementary_chamber_sensors: tuple[SupplementarySensorConfig, ...] = (),
    ) -> SimulationResult:

        if coordinator is not None:
            if not isinstance(coordinator, ExecutionCoordinator):
                raise TypeError(
                    "coordinator must be an ExecutionCoordinator"
                )

            if coordinator.runtime.recipe != self.recipe:
                raise ValueError(
                    "Coordinator recipe snapshot does not match"
                )

        if command_admission is None:
            if command_identity is not None:
                raise ValueError(
                    "command_identity requires command_admission"
                )
        else:
            if not isinstance(
                command_admission,
                SimulatedCommandAdmission,
            ):
                raise TypeError(
                    "command_admission must be "
                    "SimulatedCommandAdmission"
                )

            if not isinstance(command_identity, CommandIdentity):
                command_admission.revoke()
                raise TypeError(
                    "command_identity must be CommandIdentity"
                )

            if coordinator is not None:
                if (
                    command_identity.execution_session_id
                    != coordinator.run_id
                ):
                    command_admission.revoke()
                    raise ValueError(
                        "Command identity execution session "
                        "does not match persistent run"
                    )

            if not command_admission.is_active_identity(
                command_identity
            ):
                command_admission.revoke()
                raise ValueError(
                    "Command identity is not the active "
                    "ownership and inhibition generation"
                )

        if observer is not None and not callable(observer):
            raise TypeError("observer must be callable")

        if (
            type(report_every_s) not in (int, float)
            or not isfinite(report_every_s)
            or report_every_s <= 0
        ):
            raise ValueError(
                "report_every_s must be finite and positive"
            )

        if not isinstance(supplementary_chamber_sensors, tuple):
            raise TypeError('supplementary_chamber_sensors must be a tuple')
        if not all(
            isinstance(config, SupplementarySensorConfig)
            for config in supplementary_chamber_sensors
        ):
            raise TypeError('invalid supplementary sensor configuration')
        ids = [config.sensor_id for config in supplementary_chamber_sensors]
        if len(ids) != len(set(ids)):
            raise ValueError('duplicate supplementary sensor_id')

        runtime = (
            coordinator.runtime
            if coordinator is not None
            else FermentationRuntime(self.recipe)
        )

        plant = ThermalModel(
            initial_c=self.initial_c,
        )

        chamber_sensor = SimulatedChamberTemperatureSensor(
            "chamber-primary"
        )

        supplementary_sensors = tuple(
            (
                SimulatedChamberTemperatureSensor(config.sensor_id),
                config.offset_c,
            )
            for config in supplementary_chamber_sensors
        )

        def supplementary_measurements(now_s):
            readings = []
            failures = []

            for sensor, offset in supplementary_sensors:
                try:
                    reading = sensor.read(
                        temperature_c=plant.state.chamber_c + offset,
                        measured_at_s=now_s,
                    )
                    if not isinstance(reading, ChamberTemperatureReading):
                        raise ValueError('invalid supplementary reading type')
                    if (
                        reading.sensor_id != sensor.sensor_id
                        or reading.measured_at_s != now_s
                    ):
                        raise ValueError('invalid supplementary reading identity or timestamp')
                    readings.append(reading)
                except (OSError, ValueError, TypeError) as exc:
                    failures.append(
                        SupplementarySensorFailure(
                            sensor_id=sensor.sensor_id,
                            error=f'{type(exc).__name__}: {exc}',
                        )
                    )

            return tuple(readings), tuple(failures)

        duration_s = (
            self.recipe.total_duration_minutes * 60.0
        )

        started = False

        try:
            if coordinator is None:
                runtime.start(now_s=0.0)
            else:
                coordinator.start(now_s=0.0)

            started = True

            samples = []

            minimum = float("inf")
            maximum = float("-inf")

            heating_seconds = 0.0
            cooling_seconds = 0.0
            idle_seconds = 0.0

            now_s = 0.0
            next_report_s = 0.0

            while now_s < duration_s:

                dt_s = min(
                    self.step_s,
                    duration_s - now_s,
                )

                ambient = (
                    ambient_c(now_s)
                    if callable(ambient_c)
                    else ambient_c
                )

                if (
                    type(ambient) not in (int, float)
                    or not isfinite(ambient)
                ):
                    raise ValueError(
                        "ambient temperature must be finite"
                    )

                reading = chamber_sensor.read(
                    temperature_c=plant.state.chamber_c,
                    measured_at_s=now_s,
                )

                if coordinator is None:
                    runtime.heartbeat(now_s=now_s)

                    decision = runtime.evaluate(
                        chamber_c=reading.temperature_c,
                        measured_at_s=reading.measured_at_s,
                        now_s=now_s,
                    )
                else:
                    decision = coordinator.advance(
                        chamber_c=reading.temperature_c,
                        measured_at_s=reading.measured_at_s,
                        now_s=now_s,
                    )

                if decision.state != RuntimeState.RUNNING:
                    raise RuntimeError(
                        "simulation runtime stopped: "
                        + decision.reason
                    )

                heating = decision.heating_permitted
                cooling = decision.cooling_permitted

                if command_admission is not None:
                    admitted = command_admission.admit(
                        identity=command_identity,
                        heating=heating,
                        cooling=cooling,
                    )

                    executed = command_admission.execute(
                        identity=command_identity,
                        decision=admitted,
                    )

                    heating = (
                        executed.accepted
                        and executed.mode is CommandMode.HEATING
                    )
                    cooling = (
                        executed.accepted
                        and executed.mode is CommandMode.COOLING
                    )

                if (
                    observer is not None
                    and now_s + 1e-9 >= next_report_s
                ):
                    stage = decision.stage

                    monitoring_readings, monitoring_failures = (
                        supplementary_measurements(now_s)
                    )

                    observer(
                        SimulationObservation(
                            elapsed_s=now_s,
                            stage_name=(
                                stage.name
                                if stage is not None
                                else "COMPLETE"
                            ),
                            target_c=(
                                stage.temperature_c
                                if stage is not None
                                else None
                            ),
                            chamber_c=plant.state.chamber_c,
                            food_c=plant.state.food_c,
                            progress_percent=decision.progress_percent,
                            heating_permitted=heating,
                            cooling_permitted=cooling,
                            state=decision.state,
                            supplementary_readings=monitoring_readings,
                            supplementary_failures=monitoring_failures,
                        )
                    )

                    next_report_s += report_every_s

                    while next_report_s <= now_s:
                        next_report_s += report_every_s

                if heating and cooling:
                    raise RuntimeError(
                        "simultaneous heating and cooling"
                    )

                if heating:
                    heating_seconds += dt_s
                elif cooling:
                    cooling_seconds += dt_s
                else:
                    idle_seconds += dt_s

                plant.step(
                    dt_s=dt_s,
                    ambient_c=float(ambient),
                    heating_demand=float(heating),
                    cooling_demand=float(cooling),
                )

                now_s += dt_s

                minimum = min(
                    minimum,
                    plant.state.chamber_c,
                )

                maximum = max(
                    maximum,
                    plant.state.chamber_c,
                )

                samples.append(
                    SimulationSample(
                        elapsed_s=now_s,
                        ambient_c=float(ambient),
                        chamber_c=plant.state.chamber_c,
                        vessel_c=plant.state.vessel_c,
                        food_c=plant.state.food_c,
                        progress_percent=self.recipe.progress_percent(
                            now_s / 60.0
                        ),
                        heating_permitted=heating,
                        cooling_permitted=cooling,
                    )
                )

            final_reading = chamber_sensor.read(
                temperature_c=plant.state.chamber_c,
                measured_at_s=duration_s,
            )

            if coordinator is None:
                runtime.heartbeat(now_s=duration_s)

                completion = runtime.evaluate(
                    chamber_c=final_reading.temperature_c,
                    measured_at_s=final_reading.measured_at_s,
                    now_s=duration_s,
                )
            else:
                completion = coordinator.advance(
                    chamber_c=final_reading.temperature_c,
                    measured_at_s=final_reading.measured_at_s,
                    now_s=duration_s,
                )

            if completion.state != RuntimeState.COMPLETED:
                raise RuntimeError(
                    "simulation did not complete successfully"
                )

            if (
                completion.heating_permitted
                or completion.cooling_permitted
            ):
                raise RuntimeError(
                    "actuators permitted after completion"
                )

            if observer is not None:
                monitoring_readings, monitoring_failures = (
                    supplementary_measurements(duration_s)
                )

                observer(
                    SimulationObservation(
                        elapsed_s=duration_s,
                        stage_name="COMPLETE",
                        target_c=None,
                        chamber_c=plant.state.chamber_c,
                        food_c=plant.state.food_c,
                        progress_percent=100.0,
                        heating_permitted=False,
                        cooling_permitted=False,
                        state=completion.state,
                        supplementary_readings=monitoring_readings,
                        supplementary_failures=monitoring_failures,
                    )
                )

            return SimulationResult(
                state=completion.state,
                samples=tuple(samples),
                minimum_chamber_c=minimum,
                maximum_chamber_c=maximum,
                heating_seconds=heating_seconds,
                cooling_seconds=cooling_seconds,
                idle_seconds=idle_seconds,
            )

        except Exception:
            if started:
                if coordinator is not None:
                    coordinator.abort_execution()
                else:
                    runtime.inhibit()
            raise

        finally:
            # Simulation-only authority cleanup.
            #
            # The runner must not leave previously enabled
            # command admission active after completion,
            # failure, or observer exceptions.
            #
            # This does not establish exclusive ownership
            # of physical actuator hardware.
            if command_admission is not None:
                command_admission.revoke()
