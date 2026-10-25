"""
FermentaLab database integrity acceptance tests.

All tests use temporary databases.
Persistent application databases are never modified.
"""

import sqlite3
import tempfile
import unittest

from contextlib import closing
from pathlib import Path

from fermentalab.storage import RecipeStore, StorageError


class TestDatabaseIntegrity(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_missing_database_created(self):
        path = self.root / "new.db"

        self.assertFalse(path.exists())

        RecipeStore(path).initialise()

        self.assertTrue(path.exists())

        with closing(sqlite3.connect(path)) as connection:
            version = connection.execute(
                "SELECT value FROM metadata "
                "WHERE key = 'schema_version'"
            ).fetchone()[0]

        self.assertEqual(version, "3")

    def test_existing_zero_byte_database_rejected(self):
        path = self.root / "empty.db"
        path.touch()

        self.assertEqual(path.stat().st_size, 0)

        with self.assertRaises(StorageError):
            RecipeStore(path).initialise()

        self.assertEqual(path.stat().st_size, 0)

    def test_schema_v3_invalid_column_rejected(self):
        path = self.root / "mismatch.db"

        RecipeStore(path).initialise()

        with closing(sqlite3.connect(path)) as connection:
            row = connection.execute(
                """
                SELECT sql
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'fermentation_runs'
                """
            ).fetchone()

            self.assertIsNotNone(row)

            original_sql = row[0]

            original_column = (
                "elapsed_seconds INTEGER NOT NULL DEFAULT 0"
            )

            invalid_column = (
                "elapsed_seconds TEXT NOT NULL DEFAULT 0"
            )

            self.assertEqual(
                original_sql.count(original_column),
                1,
            )

            mutated_sql = original_sql.replace(
                original_column,
                invalid_column,
                1,
            )

            mutated_sql = mutated_sql.replace(
                "CREATE TABLE fermentation_runs",
                "CREATE TABLE fermentation_runs_invalid",
                1,
            )

            with connection:
                connection.execute(mutated_sql)

                connection.execute(
                    "DROP TABLE fermentation_runs"
                )

                connection.execute(
                    """
                    ALTER TABLE fermentation_runs_invalid
                    RENAME TO fermentation_runs
                    """
                )

        with self.assertRaises(StorageError):
            RecipeStore(path).initialise()

    def test_schema_rejection_preserves_database(self):
        path = self.root / "preserve.db"

        RecipeStore(path).initialise()

        with closing(sqlite3.connect(path)) as connection:
            row = connection.execute(
                """
                SELECT sql
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'fermentation_runs'
                """
            ).fetchone()

            self.assertIsNotNone(row)

            original_sql = row[0]

            original_column = (
                "elapsed_seconds INTEGER NOT NULL DEFAULT 0"
            )

            invalid_column = (
                "elapsed_seconds TEXT NOT NULL DEFAULT 0"
            )

            self.assertEqual(
                original_sql.count(original_column),
                1,
            )

            mutated_sql = original_sql.replace(
                original_column,
                invalid_column,
                1,
            )

            mutated_sql = mutated_sql.replace(
                "CREATE TABLE fermentation_runs",
                "CREATE TABLE fermentation_runs_invalid",
                1,
            )

            with connection:
                connection.execute(mutated_sql)

                connection.execute(
                    "DROP TABLE fermentation_runs"
                )

                connection.execute(
                    """
                    ALTER TABLE fermentation_runs_invalid
                    RENAME TO fermentation_runs
                    """
                )

        before = path.read_bytes()

        with self.assertRaises(StorageError):
            RecipeStore(path).initialise()

        after = path.read_bytes()

        self.assertEqual(before, after)

    def test_unexpected_table_rejected(self):
        path = self.root / "unexpected.db"

        RecipeStore(path).initialise()

        with closing(sqlite3.connect(path)) as connection:
            connection.execute(
                "CREATE TABLE unexpected_table (id INTEGER)"
            )

        with self.assertRaises(StorageError):
            RecipeStore(path).initialise()

    def test_incomplete_database_rejected(self):
        path = self.root / "incomplete.db"

        with closing(sqlite3.connect(path)) as connection:
            connection.execute(
                "CREATE TABLE metadata (key TEXT PRIMARY KEY)"
            )

        with self.assertRaises(StorageError):
            RecipeStore(path).initialise()
