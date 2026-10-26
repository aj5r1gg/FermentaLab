import logging
import os
import unittest

from pathlib import Path

from classes.recipes import Recipes
from classes.currentrecipe import CurrentRecipe
from classes.config import Config


UPSTREAM = Path("/workspace/upstream/software/src")


class TestUpstreamCompatibility(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.original_directory = Path.cwd()
        os.chdir(UPSTREAM)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.original_directory)

    def test_recipes_class_loads(self):
        recipes = Recipes(logging)

        self.assertIsInstance(recipes.data, list)
        self.assertEqual(len(recipes.data), 2)

    def test_recipe_names(self):
        recipes = Recipes(logging)

        names = [recipe["Name"] for recipe in recipes.data]

        self.assertIn("Salumi Toscano", names)
        self.assertIn("Saucisson Sec", names)

    def test_recipe_stage_structure(self):
        recipes = Recipes(logging)

        for recipe in recipes.data:
            for stage_name in ("Incubate", "Cure", "Finish"):
                self.assertIn(stage_name, recipe)

                stage = recipe[stage_name]

                self.assertIn("Cycle Time", stage)
                self.assertIn("Cycle Time Toggle", stage)
                self.assertIn("Temperature", stage)
                self.assertIn("Humidity", stage)

    def test_recipe_durations(self):
        recipes = Recipes(logging)

        expected = {
            "Salumi Toscano": 852,
            "Saucisson Sec": 612,
        }

        for recipe in recipes.data:
            duration = 0

            for stage_name in ("Incubate", "Cure", "Finish"):
                stage = recipe[stage_name]

                duration += (
                    stage["Cycle Time Toggle"]
                    * stage["Cycle Time"]
                )

            self.assertEqual(
                duration,
                expected[recipe["Name"]],
            )

    def test_current_recipe_loads(self):
        current = CurrentRecipe(logging)

        self.assertIsInstance(current.data, dict)

        self.assertIn("Database", current.data)
        self.assertIn("Started", current.data)
        self.assertIn("Recipe Name", current.data)
        self.assertIn("Current Checkpoint", current.data)

    def test_config_loads(self):
        config = Config(logging)

        self.assertIsInstance(config.data, dict)

        self.assertIn("Temperature Format", config.data)
        self.assertIn("Database Naming Pattern", config.data)
        self.assertIn("Relays", config.data)

    def test_upstream_files_remain_read_only(self):
        self.assertFalse(
            os.access(
                UPSTREAM / "recipes.json",
                os.W_OK,
            )
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
