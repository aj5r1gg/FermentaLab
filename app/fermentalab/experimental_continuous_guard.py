"""Experimental continuous predictive heating guard.

SIMULATION ONLY.

This module has no physical actuator authority and must not be used
to bypass independent FermentaLab safety domains.
"""

from math import isfinite

from fermentalab.predictive_control import (
    PredictiveController,
    PredictiveDecision,
)


class ExperimentalContinuousGuard(PredictiveController):
    """Continuous predictive guard using the existing three-node model."""

    def __init__(self, *, guard_margin_c=0.0, **kwargs):
        if (
            type(guard_margin_c) not in (int, float)
            or not isfinite(guard_margin_c)
            or not 0.0 <= guard_margin_c <= 1.0
        ):
            raise ValueError("invalid guard margin")

        super().__init__(**kwargs)

        self.guard_margin_c = float(guard_margin_c)

    def continuous_cap(
        self,
        *,
        chamber_c,
        vessel_c,
        food_c,
        target_c,
    ):
        """Return maximum feasible constant heating demand.

        The constraint applies to every forecast timestep.

        Returns:
            (heating_cap, feasible)

        If zero heating already violates the forecast ceiling,
        feasible is False and heating_cap is zero.
        """

        values = (
            chamber_c,
            vessel_c,
            food_c,
            target_c,
        )

        if any(
            type(value) not in (int, float)
            or not isfinite(value)
            for value in values
        ):
            raise ValueError("non-finite forecast input")

        p = self.parameters

        limit = target_c + self.guard_margin_c

        a0 = float(chamber_c)
        v0 = float(vessel_c)
        f0 = float(food_c)

        da = 0.0
        dv = 0.0
        df = 0.0

        cap = 1.0
        tolerance = 1e-10

        if f0 > limit:
            return 0.0, False

        dt = self.step_s

        for _ in range(self.horizon_s // dt):

            q_av = (
                p.chamber_vessel_conductance_w_per_c
                * (a0 - v0)
            )

            q_vf = (
                p.vessel_food_conductance_w_per_c
                * (v0 - f0)
            )

            na0 = a0 + dt * (
                p.ambient_conductance_w_per_c
                * (self.ambient_c - a0)
                - q_av
            ) / p.chamber_capacity_j_per_c

            nv0 = v0 + dt * (
                q_av - q_vf
            ) / p.vessel_capacity_j_per_c

            nf0 = f0 + dt * (
                q_vf
            ) / p.food_capacity_j_per_c

            dq_av = (
                p.chamber_vessel_conductance_w_per_c
                * (da - dv)
            )

            dq_vf = (
                p.vessel_food_conductance_w_per_c
                * (dv - df)
            )

            nda = da + dt * (
                -p.ambient_conductance_w_per_c * da
                - dq_av
                + p.heater_power_w
            ) / p.chamber_capacity_j_per_c

            ndv = dv + dt * (
                dq_av - dq_vf
            ) / p.vessel_capacity_j_per_c

            ndf = df + dt * (
                dq_vf
            ) / p.food_capacity_j_per_c

            a0, v0, f0 = na0, nv0, nf0
            da, dv, df = nda, ndv, ndf

            if f0 > limit + tolerance:
                return 0.0, False

            if df > tolerance:
                allowed = (limit - f0) / df
                cap = min(cap, allowed)

            elif df < -tolerance:
                raise AssertionError(
                    "unexpected negative heating response"
                )

        return max(0.0, min(1.0, cap)), True

    def evaluate(
        self,
        *,
        measured_c,
        target_c,
        observed_at_s,
        enabled=False,
        vessel_c=None,
        chamber_c=None,
    ):
        """Evaluate PI demand with the experimental continuous guard."""

        d = self.base.evaluate(
            measured_c=measured_c,
            target_c=target_c,
            observed_at_s=observed_at_s,
            enabled=enabled,
            vessel_c=vessel_c,
            chamber_c=chamber_c,
        )

        if d.reason != "evaluated":
            self._last_guard_time = None
            self._last_guard_cap = 1.0

            return PredictiveDecision(
                0.0,
                0.0,
                d.predicted_c,
                d.reason,
            )

        if (
            vessel_c is None
            or chamber_c is None
            or d.heating_demand <= 0
        ):
            return PredictiveDecision(
                d.heating_demand,
                d.cooling_demand,
                d.predicted_c,
                "baseline",
            )

        if measured_c < target_c - 3.0:
            self._last_guard_time = None
            self._last_guard_cap = 1.0

            return PredictiveDecision(
                d.heating_demand,
                0.0,
                d.predicted_c,
                "warmup",
            )

        if (
            self._last_guard_time is not None
            and observed_at_s - self._last_guard_time < 30
        ):
            return PredictiveDecision(
                min(
                    d.heating_demand,
                    self._last_guard_cap,
                ),
                0.0,
                d.predicted_c,
                "guarded-cached",
            )

        cap, feasible = self.continuous_cap(
            chamber_c=chamber_c,
            vessel_c=vessel_c,
            food_c=measured_c,
            target_c=target_c,
        )

        self._last_guard_time = observed_at_s
        self._last_guard_cap = cap

        return PredictiveDecision(
            min(d.heating_demand, cap),
            0.0,
            d.predicted_c,
            "guarded" if feasible else "guarded-infeasible",
        )
