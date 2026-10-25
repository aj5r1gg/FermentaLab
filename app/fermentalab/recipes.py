"""
FermentaLab recipe model.

Conceptually derived from the Open Fermentation Project's
recipe lifecycle and environmental target model.

No hardware control is performed by this module.
"""

from dataclasses import dataclass
from math import isfinite
from typing import Any


class RecipeValidationError(ValueError):
    """Raised when a recipe is invalid."""


def require_mapping(value: Any, field: str) -> dict:
    if not isinstance(value, dict):
        raise RecipeValidationError(f"{field} must be an object")
    return value


def require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecipeValidationError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def require_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(
        value, (int, float)
    ):
        raise RecipeValidationError(
            f"{field} must be a number"
        )

    number = float(value)

    if not isfinite(number):
        raise RecipeValidationError(
            f"{field} must be finite"
        )

    return number


@dataclass(frozen=True)
class RecipeStage:
    name: str
    duration_minutes: int
    temperature_c: float
    humidity_percent: float | None

    @classmethod
    def from_dict(cls, data: dict) -> "RecipeStage":
        data = require_mapping(data, "stage")

        required = {
            "name",
            "duration_minutes",
            "temperature_c",
            "humidity_percent",
        }

        if set(data) != required:
            raise RecipeValidationError(
                "stage fields must be exactly: "
                + ", ".join(sorted(required))
            )

        name = require_string(data["name"], "stage.name")

        duration = data["duration_minutes"]

        if (
            isinstance(duration, bool)
            or not isinstance(duration, int)
            or duration <= 0
        ):
            raise RecipeValidationError(
                "stage.duration_minutes must be a positive integer"
            )

        temperature = require_number(
            data["temperature_c"],
            "stage.temperature_c",
        )

        if not -20.0 <= temperature <= 100.0:
            raise RecipeValidationError(
                "stage.temperature_c is outside the "
                "supported engineering range"
            )

        humidity = data["humidity_percent"]

        if humidity is not None:
            humidity = require_number(
                humidity,
                "stage.humidity_percent",
            )

            if not 0.0 <= humidity <= 100.0:
                raise RecipeValidationError(
                    "stage.humidity_percent must be "
                    "between 0 and 100"
                )

        return cls(
            name=name,
            duration_minutes=duration,
            temperature_c=temperature,
            humidity_percent=humidity,
        )


@dataclass(frozen=True)
class Recipe:
    schema_version: int
    id: str
    name: str
    stages: tuple[RecipeStage, ...]

    @classmethod
    def from_dict(cls, data: dict) -> "Recipe":
        data = require_mapping(data, "recipe")

        required = {
            "schema_version",
            "id",
            "name",
            "stages",
        }

        if set(data) != required:
            raise RecipeValidationError(
                "recipe fields must be exactly: "
                + ", ".join(sorted(required))
            )

        version = data["schema_version"]

        if type(version) is not int or version != 1:
            raise RecipeValidationError(
                "unsupported recipe schema version"
            )

        recipe_id = require_string(data["id"], "recipe.id")
        name = require_string(data["name"], "recipe.name")

        stages_data = data["stages"]

        if not isinstance(stages_data, list) or not stages_data:
            raise RecipeValidationError(
                "recipe.stages must be a non-empty array"
            )

        stages = tuple(
            RecipeStage.from_dict(stage)
            for stage in stages_data
        )

        return cls(
            schema_version=version,
            id=recipe_id,
            name=name,
            stages=stages,
        )

    @property
    def total_duration_minutes(self) -> int:
        return sum(
            stage.duration_minutes
            for stage in self.stages
        )

    def stage_at(
        self,
        elapsed_minutes: int | float,
    ) -> RecipeStage | None:
        """
        Return the active stage at the given elapsed time.

        Stage intervals are half-open:
        [start, end).

        None means the recipe has completed.
        """

        elapsed = require_number(
            elapsed_minutes,
            "elapsed_minutes",
        )

        if elapsed < 0:
            raise ValueError(
                "elapsed_minutes cannot be negative"
            )

        boundary = 0

        for stage in self.stages:
            boundary += stage.duration_minutes

            if elapsed < boundary:
                return stage

        return None

    def progress_percent(
        self,
        elapsed_minutes: int | float,
    ) -> float:
        elapsed = require_number(
            elapsed_minutes,
            "elapsed_minutes",
        )

        if elapsed < 0:
            raise ValueError(
                "elapsed_minutes cannot be negative"
            )

        return min(
            100.0,
            100.0 * elapsed / self.total_duration_minutes,
        )
