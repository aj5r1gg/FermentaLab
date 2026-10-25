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
    ) -> SimulationResult:

        runtime = FermentationRuntime(self.recipe)

        plant = ThermalModel(
            initial_c=self.initial_c,
        )

        duration_s = (
            self.recipe.total_duration_minutes * 60.0
        )

        runtime.start(now_s=0.0)

        samples = []

        minimum = float("inf")
        maximum = float("-inf")

        heating_seconds = 0.0
        cooling_seconds = 0.0
        idle_seconds = 0.0

        now_s = 0.0

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

            runtime.heartbeat(now_s=now_s)

            decision = runtime.evaluate(
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

        runtime.heartbeat(now_s=duration_s)

        completion = runtime.evaluate(
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

        return SimulationResult(
            state=completion.state,
            samples=tuple(samples),
            minimum_chamber_c=minimum,
            maximum_chamber_c=maximum,
            heating_seconds=heating_seconds,
            cooling_seconds=cooling_seconds,
            idle_seconds=idle_seconds,
        )
