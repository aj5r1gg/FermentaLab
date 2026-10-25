import math
import unittest

from fermentalab.recipes import (
    Recipe,
    RecipeValidationError,
)


def example_recipe():
    return {
        "schema_version": 1,
        "id": "example-fermentation",
        "name": "Example Fermentation",
        "stages": [
            {
                "name": "Stage One",
                "duration_minutes": 60,
                "temperature_c": 35.0,
                "humidity_percent": None,
            },
            {
                "name": "Stage Two",
                "duration_minutes": 120,
                "temperature_c": 25.0,
                "humidity_percent": 75.0,
            },
        ],
    }


class TestRecipeEngine(unittest.TestCase):

    def test_valid_recipe(self):
        recipe = Recipe.from_dict(example_recipe())
        self.assertEqual(recipe.name, "Example Fermentation")

    def test_total_duration(self):
        recipe = Recipe.from_dict(example_recipe())
        self.assertEqual(recipe.total_duration_minutes, 180)

    def test_first_stage(self):
        recipe = Recipe.from_dict(example_recipe())
        self.assertEqual(
            recipe.stage_at(0).name,
            "Stage One",
        )

    def test_stage_boundary(self):
        recipe = Recipe.from_dict(example_recipe())
        self.assertEqual(
            recipe.stage_at(60).name,
            "Stage Two",
        )

    def test_last_instant(self):
        recipe = Recipe.from_dict(example_recipe())
        self.assertEqual(
            recipe.stage_at(179.999).name,
            "Stage Two",
        )

    def test_recipe_completion(self):
        recipe = Recipe.from_dict(example_recipe())
        self.assertIsNone(recipe.stage_at(180))

    def test_progress(self):
        recipe = Recipe.from_dict(example_recipe())
        self.assertAlmostEqual(
            recipe.progress_percent(90),
            50.0,
        )

    def test_progress_clamped(self):
        recipe = Recipe.from_dict(example_recipe())
        self.assertEqual(
            recipe.progress_percent(1000),
            100.0,
        )

    def test_reject_zero_duration(self):
        data = example_recipe()
        data["stages"][0]["duration_minutes"] = 0

        with self.assertRaises(RecipeValidationError):
            Recipe.from_dict(data)

    def test_reject_boolean_duration(self):
        data = example_recipe()
        data["stages"][0]["duration_minutes"] = True

        with self.assertRaises(RecipeValidationError):
            Recipe.from_dict(data)

    def test_reject_invalid_humidity(self):
        data = example_recipe()
        data["stages"][0]["humidity_percent"] = 120

        with self.assertRaises(RecipeValidationError):
            Recipe.from_dict(data)

    def test_reject_nan_temperature(self):
        data = example_recipe()
        data["stages"][0]["temperature_c"] = math.nan

        with self.assertRaises(RecipeValidationError):
            Recipe.from_dict(data)

    def test_reject_empty_stages(self):
        data = example_recipe()
        data["stages"] = []

        with self.assertRaises(RecipeValidationError):
            Recipe.from_dict(data)

    def test_reject_unknown_fields(self):
        data = example_recipe()
        data["unexpected"] = "value"

        with self.assertRaises(RecipeValidationError):
            Recipe.from_dict(data)

    def test_reject_negative_elapsed(self):
        recipe = Recipe.from_dict(example_recipe())

        with self.assertRaises(ValueError):
            recipe.stage_at(-1)

    def test_reject_unsupported_version(self):
        data = example_recipe()
        data["schema_version"] = 2

        with self.assertRaises(RecipeValidationError):
            Recipe.from_dict(data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
