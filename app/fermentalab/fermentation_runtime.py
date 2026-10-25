"""
FermentaLab simulation-only fermentation runtime.

Coordinates recipe stages with the existing supervisory controller.

This module does not control physical hardware and does not
establish physical actuator authority.
"""

from dataclasses import dataclass
from enum import Enum
from math import isfinite

from fermentalab.recipes import Recipe, RecipeStage
from fermentalab.supervisor import (
    SupervisoryController,
    SupervisorDecision,
    SupervisorState,
)


class RuntimeState(Enum):
    INHIBITED = "inhibited"
    RUNNING = "running"
    COMPLETED = "completed"
    FAULT = "fault"


@dataclass(frozen=True)
class RuntimeDecision:
    state: RuntimeState
    stage: RecipeStage | None
    supervisor: SupervisorDecision
    progress_percent: float
    reason: str

    @property
    def heating_permitted(self) -> bool:
        return self.supervisor.heating_permitted

    @property
    def cooling_permitted(self) -> bool:
        return self.supervisor.cooling_permitted


class FermentationRuntime:
    """
    Simulation-only recipe execution coordinator.

    All timestamps use one monotonic timebase.

    The supervisor remains responsible for temperature-control
    decisions, measurement freshness, watchdog checks, and
    simulated actuator authority.
    """

    def __init__(
        self,
        recipe: Recipe,
        *,
        supervisor: SupervisoryController | None = None,
    ):
        if not isinstance(recipe, Recipe):
            raise TypeError("recipe must be a Recipe")

        self.recipe = recipe

        self.supervisor = (
            supervisor
            if supervisor is not None
            else SupervisoryController()
        )

        if not isinstance(
            self.supervisor,
            SupervisoryController,
        ):
            raise TypeError(
                "supervisor must be a SupervisoryController"
            )

        self._state = RuntimeState.INHIBITED
        self._started_at_s = None

    @property
    def state(self) -> RuntimeState:
        return self._state

    @staticmethod
    def _valid_time(value) -> bool:
        return (
            type(value) in (int, float)
            and isfinite(value)
        )

    def _result(
        self,
        *,
        stage,
        supervisor_decision,
        progress,
        reason,
    ) -> RuntimeDecision:
        return RuntimeDecision(
            state=self._state,
            stage=stage,
            supervisor=supervisor_decision,
            progress_percent=progress,
            reason=reason,
        )

    def start(self, *, now_s: float) -> RuntimeDecision:
        if self._state != RuntimeState.INHIBITED:
            raise RuntimeError(
                "runtime must be inhibited before starting"
            )

        if not self._valid_time(now_s):
            raise ValueError(
                "now_s must be finite"
            )

        if self.supervisor.state != SupervisorState.INHIBITED:
            raise RuntimeError(
                "supervisor must be inhibited before starting"
            )

        decision = self.supervisor.activate(now_s=now_s)

        if self.supervisor.state != SupervisorState.ACTIVE:
            self._state = RuntimeState.FAULT
            return self._result(
                stage=None,
                supervisor_decision=decision,
                progress=0.0,
                reason="supervisor activation failed",
            )

        self._started_at_s = float(now_s)
        self._state = RuntimeState.RUNNING

        return self._result(
            stage=self.recipe.stage_at(0),
            supervisor_decision=decision,
            progress=0.0,
            reason="fermentation started",
        )

    def heartbeat(self, *, now_s: float) -> SupervisorDecision:
        if self._state != RuntimeState.RUNNING:
            if self.supervisor.state == SupervisorState.FAULT:
                return self.supervisor.heartbeat(now_s=now_s)

            return self.supervisor.inhibit()

        decision = self.supervisor.heartbeat(now_s=now_s)

        if self.supervisor.state == SupervisorState.FAULT:
            self._state = RuntimeState.FAULT

        return decision

    def evaluate(
        self,
        *,
        chamber_c: float,
        measured_at_s: float,
        now_s: float,
    ) -> RuntimeDecision:

        if self._state != RuntimeState.RUNNING:
            raise RuntimeError(
                "runtime is not running"
            )

        if not self._valid_time(now_s):
            decision = self.supervisor.evaluate(
                measured_c=chamber_c,
                target_c=self.recipe.stages[0].temperature_c,
                measured_at_s=measured_at_s,
                now_s=now_s,
            )
            self._state = RuntimeState.FAULT
            return self._result(
                stage=None,
                supervisor_decision=decision,
                progress=0.0,
                reason="invalid runtime time",
            )

        elapsed_s = float(now_s) - self._started_at_s

        if elapsed_s < 0:
            decision = self.supervisor.evaluate(
                measured_c=chamber_c,
                target_c=self.recipe.stages[0].temperature_c,
                measured_at_s=measured_at_s,
                now_s=now_s,
            )
            self._state = RuntimeState.FAULT
            return self._result(
                stage=None,
                supervisor_decision=decision,
                progress=0.0,
                reason="runtime clock regression",
            )

        elapsed_minutes = elapsed_s / 60.0

        stage = self.recipe.stage_at(elapsed_minutes)

        progress = self.recipe.progress_percent(
            elapsed_minutes
        )

        if stage is None:
            # A recipe boundary must not conceal an expired watchdog.
            decision = self.supervisor.heartbeat(now_s=now_s)

            if self.supervisor.state == SupervisorState.FAULT:
                self._state = RuntimeState.FAULT
                return self._result(
                    stage=None,
                    supervisor_decision=decision,
                    progress=progress,
                    reason="supervisory fault at completion",
                )

            decision = self.supervisor.inhibit()
            self._state = RuntimeState.COMPLETED

            return self._result(
                stage=None,
                supervisor_decision=decision,
                progress=100.0,
                reason="fermentation completed",
            )

        decision = self.supervisor.evaluate(
            measured_c=chamber_c,
            target_c=stage.temperature_c,
            measured_at_s=measured_at_s,
            now_s=now_s,
        )

        if self.supervisor.state == SupervisorState.FAULT:
            self._state = RuntimeState.FAULT

        return self._result(
            stage=stage,
            supervisor_decision=decision,
            progress=progress,
            reason=(
                "supervisory fault"
                if self._state == RuntimeState.FAULT
                else "fermentation stage evaluated"
            ),
        )

    def inhibit(self) -> RuntimeDecision:
        if (
            self._state == RuntimeState.FAULT
            or self.supervisor.state == SupervisorState.FAULT
        ):
            self._state = RuntimeState.FAULT

            decision = self.supervisor.fault_status()

            return self._result(
                stage=None,
                supervisor_decision=decision,
                progress=0.0,
                reason="fault clearance required",
            )

        decision = self.supervisor.inhibit()
        self._state = RuntimeState.INHIBITED
        self._started_at_s = None

        return self._result(
            stage=None,
            supervisor_decision=decision,
            progress=0.0,
            reason="fermentation inhibited",
        )

    def clear_fault(self) -> RuntimeDecision:
        if self._state != RuntimeState.FAULT:
            raise RuntimeError(
                "runtime has no latched fault"
            )

        if self.supervisor.state != SupervisorState.FAULT:
            raise RuntimeError(
                "supervisor has no latched fault"
            )

        decision = self.supervisor.clear_fault()

        if self.supervisor.state != SupervisorState.INHIBITED:
            raise RuntimeError(
                "supervisor fault clearance failed"
            )

        self._state = RuntimeState.INHIBITED
        self._started_at_s = None

        return self._result(
            stage=None,
            supervisor_decision=decision,
            progress=0.0,
            reason="fault cleared; activation required",
        )
