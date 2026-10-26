"""
FermentaLab simulation-only execution coordinator.

Connects a persistent fermentation-run snapshot to a fresh
FermentationRuntime instance.

This module does not operate physical hardware, provide
independent actuator permission, or establish food-safety
qualification.
"""

from fermentalab.fermentation_runtime import (
    FermentationRuntime,
    RuntimeState,
)
from fermentalab.storage import RecipeStore, StorageError


class ExecutionCoordinator:
    """
    Coordinate simulation-only persistent-run execution.

    Supports activation, runtime advancement, completion,
    and abnormal-termination handling.

    Runtime authority remains with FermentationRuntime and
    its SupervisoryController. SQLite lifecycle status is
    not actuator authority.
    """

    def __init__(
        self,
        *,
        store: RecipeStore,
        run_id: str,
    ):
        if not isinstance(store, RecipeStore):
            raise TypeError(
                "store must be a RecipeStore"
            )

        if not isinstance(run_id, str) or not run_id:
            raise ValueError(
                "run_id must be a non-empty string"
            )

        stored_run = store.get_run(run_id)

        if stored_run is None:
            raise StorageError(
                f"Fermentation run not found: {run_id}"
            )

        if stored_run["status"] != "created":
            raise StorageError(
                "Execution requires a newly created run"
            )

        self.store = store
        self.run_id = run_id

        # The run snapshot, not the mutable recipe catalogue,
        # determines execution targets.
        self.runtime = FermentationRuntime(
            stored_run["recipe"]
        )

        self._started = False

    def advance(
        self,
        *,
        chamber_c: float,
        measured_at_s: float,
        now_s: float,
    ):
        """
        Advance a running fermentation using a chamber measurement.

        Simulation-only execution. No physical actuator control.
        """
        if not self._started:
            raise RuntimeError(
                "Execution coordinator has not started"
            )

        if self.runtime.state != RuntimeState.RUNNING:
            raise RuntimeError(
                "Execution runtime is not running"
            )

        # Persistent lifecycle state must remain eligible
        # for execution. An in-memory runtime cannot
        # override a paused, cancelled, failed, completed,
        # or missing persistent run.
        try:
            stored_run = self.store.get_run(self.run_id)

            if (
                stored_run is None
                or stored_run["status"] != "running"
            ):
                self.runtime.inhibit()

                status = (
                    "missing"
                    if stored_run is None
                    else stored_run["status"]
                )

                raise RuntimeError(
                    "Persistent run is not running: "
                    + status
                )

        except Exception:
            self.runtime.inhibit()
            raise

        try:
            self.runtime.heartbeat(now_s=now_s)

            if self.runtime.state == RuntimeState.FAULT:
                raise RuntimeError(
                    "Supervisory heartbeat fault"
                )

            decision = self.runtime.evaluate(
                chamber_c=chamber_c,
                measured_at_s=measured_at_s,
                now_s=now_s,
            )

            # Evaluation may have overlapped an external
            # lifecycle transition. Revalidate persistent
            # state before accepting the control decision.
            #
            # This is a simulation-level consistency guard,
            # not independent physical actuator permission.
            stored_run = self.store.get_run(self.run_id)

            if (
                stored_run is None
                or stored_run["status"] != "running"
            ):
                status = (
                    "missing"
                    if stored_run is None
                    else stored_run["status"]
                )

                raise RuntimeError(
                    "Persistent run changed during evaluation: "
                    + status
                )

            if (
                decision.heating_permitted
                and decision.cooling_permitted
            ):
                raise RuntimeError(
                    "Simultaneous heating and cooling"
                )

            if decision.state == RuntimeState.COMPLETED:
                self.store.transition_run(
                    self.run_id,
                    "complete",
                )

            elif decision.state == RuntimeState.FAULT:
                raise RuntimeError(
                    "Fermentation runtime fault: "
                    + decision.reason
                )

            elif decision.state != RuntimeState.RUNNING:
                raise RuntimeError(
                    "Unexpected fermentation runtime state"
                )

            return decision

        except Exception:
            self.abort_execution()
            raise

    def abort_execution(self):
        """
        Inhibit a coordinated simulation after abnormal termination.

        If the persistent run is still RUNNING, record FAILED.

        Other persistent lifecycle states are preserved.

        This operation does not control physical hardware.
        """
        self.runtime.inhibit()

        stored_run = self.store.get_run(self.run_id)

        if stored_run is None:
            raise StorageError(
                "Persistent run missing during execution abort"
            )

        if stored_run["status"] != "running":
            return stored_run

        try:
            return self.store.transition_run(
                self.run_id,
                "fail",
                allowed_from=("running",),
            )

        except StorageError:
            # A competing lifecycle transition may have
            # won after our initial RUNNING observation.
            #
            # Preserve the new state only when it is no
            # longer RUNNING. If RUNNING remains, cleanup
            # has genuinely failed and the storage error
            # must propagate.
            current = self.store.get_run(self.run_id)

            if (
                current is not None
                and current["status"] != "running"
            ):
                return current

            raise

    def start(self, *, now_s: float):
        """
        Start a fresh runtime and persist its running state.

        Starting does not itself permit heating or cooling.

        This is an initial simulation-only integration
        boundary, not a complete crash-safe execution
        protocol.
        """
        if self._started:
            raise RuntimeError(
                "Execution coordinator already started"
            )

        stored_run = self.store.get_run(self.run_id)

        if stored_run is None:
            raise StorageError(
                "Fermentation run no longer exists"
            )

        if stored_run["status"] != "created":
            raise StorageError(
                "Persistent run is not eligible to start"
            )

        if stored_run["recipe"] != self.runtime.recipe:
            raise StorageError(
                "Persistent recipe snapshot changed"
            )

        # Persist the lifecycle transition before activating
        # the supervisory runtime. A CREATED database record
        # must never correspond to an active runtime.
        self.store.transition_run(
            self.run_id,
            "start",
        )

        try:
            decision = self.runtime.start(now_s=now_s)

            if (
                decision.state != RuntimeState.RUNNING
                or decision.heating_permitted
                or decision.cooling_permitted
            ):
                raise RuntimeError(
                    "Runtime activation did not produce "
                    "a safe running state"
                )

            # Runtime activation may overlap an external
            # lifecycle transition. Revalidate persistence
            # before accepting successful activation.
            #
            # This is simulation-level consistency checking,
            # not independent physical actuator permission.
            stored_run = self.store.get_run(self.run_id)

            if (
                stored_run is None
                or stored_run["status"] != "running"
            ):
                status = (
                    "missing"
                    if stored_run is None
                    else stored_run["status"]
                )

                raise RuntimeError(
                    "Persistent run changed during activation: "
                    + status
                )

        except Exception:
            # Inhibit the runtime and record failure only
            # if the persistent run remains RUNNING.
            #
            # Preserve competing cancellation, pause,
            # completion, or failure transitions.
            self.abort_execution()
            raise

        self._started = True

        return decision
