"""
FermentaLab adversarial schema qualification.

All mutations operate on temporary SQLite databases.
Persistent application data is never modified.
"""

import sqlite3
import tempfile
import unittest

from contextlib import closing
from pathlib import Path

from fermentalab.storage import RecipeStore, StorageError


class TestAdversarialSchema(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "adversarial.db"

        RecipeStore(self.database).initialise()

    def tearDown(self):
        self.temp.cleanup()

    def mutate_schema(self, table, original, replacement):
        """
        Rebuild one table with a modified CREATE statement.

        The database contains no application records.
        """

        with closing(sqlite3.connect(self.database)) as connection:

            row = connection.execute(
                """
                SELECT sql
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = ?
                """,
                (table,),
            ).fetchone()

            if row is None:
                raise AssertionError("Missing source table")

            sql = row[0]

            if sql.count(original) != 1:
                raise AssertionError(
                    "Mutation target not unique: " + original
                )

            mutated = sql.replace(original, replacement, 1)

            temporary = table + "_adversarial"

            prefix = "CREATE TABLE " + table

            if not mutated.startswith(prefix):
                raise AssertionError(
                    "Unexpected CREATE TABLE format"
                )

            mutated = mutated.replace(
                prefix,
                "CREATE TABLE " + temporary,
                1,
            )

            with connection:

                connection.execute("PRAGMA foreign_keys = OFF")

                connection.execute(mutated)

                connection.execute(
                    f"DROP TABLE {table}"
                )

                connection.execute(
                    f"ALTER TABLE {temporary} RENAME TO {table}"
                )

            connection.execute("PRAGMA foreign_keys = ON")

    def assert_schema_rejected(self):
        with self.assertRaises(StorageError):
            RecipeStore(self.database).initialise()

    def test_elapsed_type_mutation(self):
        self.mutate_schema(
            "fermentation_runs",
            "elapsed_seconds INTEGER NOT NULL DEFAULT 0",
            "elapsed_seconds TEXT NOT NULL DEFAULT 0",
        )

        self.assert_schema_rejected()

    def test_snapshot_nullability_mutation(self):
        self.mutate_schema(
            "fermentation_runs",
            "recipe_snapshot TEXT NOT NULL",
            "recipe_snapshot TEXT",
        )

        self.assert_schema_rejected()

    def test_elapsed_default_mutation(self):
        self.mutate_schema(
            "fermentation_runs",
            "elapsed_seconds INTEGER NOT NULL DEFAULT 0",
            "elapsed_seconds INTEGER NOT NULL DEFAULT 1",
        )

        self.assert_schema_rejected()

    def test_elapsed_check_removed(self):
        self.mutate_schema(
            "fermentation_runs",
            "CHECK (elapsed_seconds >= 0)",
            "",
        )

        self.assert_schema_rejected()

    def test_status_check_removed(self):
        self.mutate_schema(
            "fermentation_runs",
            """CHECK (
                            status IN (
                                'created',
                                'running',
                                'paused',
                                'completed',
                                'cancelled',
                                'failed'
                            )
                        )""",
            "",
        )

        self.assert_schema_rejected()

    def test_recipe_name_nullability_mutation(self):
        self.mutate_schema(
            "recipes",
            "name TEXT NOT NULL",
            "name TEXT",
        )

        self.assert_schema_rejected()
