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

from fermentalab.execution_coordinator import (
    ExecutionCoordinator,
)
from fermentalab.fermentation_runtime import (
    FermentationRuntime,
    RuntimeState,
)
from fermentalab.recipes import Recipe
from fermentalab.thermal_model import ThermalModel


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
        observer=None,
        report_every_s: float = 900.0,
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

        runtime = (
            coordinator.runtime
            if coordinator is not None
            else FermentationRuntime(self.recipe)
        )

        plant = ThermalModel(
            initial_c=self.initial_c,
        )

        duration_s = (
            self.recipe.total_duration_minutes * 60.0
        )

        if coordinator is None:
            runtime.start(now_s=0.0)
        else:
            coordinator.start(now_s=0.0)

        try:
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

                if coordinator is None:
                    runtime.heartbeat(now_s=now_s)

                    decision = runtime.evaluate(
                        chamber_c=plant.state.chamber_c,
                        measured_at_s=now_s,
                        now_s=now_s,
                    )
                else:
                    decision = coordinator.advance(
                        chamber_c=plant.state.chamber_c,
                        measured_at_s=now_s,
                        now_s=now_s,
                    )

                if decision.state != RuntimeState.RUNNING:
                    raise RuntimeError(
                        "simulation runtime stopped: "
                        + decision.reason
                    )

                heating = decision.heating_permitted
                cooling = decision.cooling_permitted

                if (
                    observer is not None
                    and now_s + 1e-9 >= next_report_s
                ):
                    stage = decision.stage

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

            if coordinator is None:
                runtime.heartbeat(now_s=duration_s)

                completion = runtime.evaluate(
                    chamber_c=plant.state.chamber_c,
                    measured_at_s=duration_s,
                    now_s=duration_s,
                )
            else:
                completion = coordinator.advance(
                    chamber_c=plant.state.chamber_c,
                    measured_at_s=duration_s,
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
            if coordinator is not None:
                coordinator.abort_execution()
            else:
                runtime.inhibit()
            raise
