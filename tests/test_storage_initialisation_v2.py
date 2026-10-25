"""
FermentaLab schema v2 initialisation acceptance tests.

These tests use temporary SQLite databases exclusively.
"""

import sqlite3
import tempfile
import unittest

from contextlib import closing
from pathlib import Path

from fermentalab.storage import RecipeStore, StorageError


class TestSchemaV2Initialisation(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "fermentalab.db"
        self.store = RecipeStore(self.database)

    def tearDown(self):
        self.temp.cleanup()

    def connect(self):
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def version(self):
        with closing(self.connect()) as connection:
            return connection.execute(
                "SELECT value FROM metadata "
                "WHERE key = 'schema_version'"
            ).fetchone()[0]

    def create_v1_database(self):
        """
        Construct a genuine v1 schema independently
        of the current RecipeStore implementation.
        """
        with closing(self.connect()) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )

                connection.execute(
                    """
                    CREATE TABLE recipes (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        recipe_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )

                connection.execute(
                    """
                    CREATE TABLE fermentation_runs (
                        id TEXT PRIMARY KEY,
                        recipe_id TEXT NOT NULL,
                        recipe_snapshot TEXT NOT NULL,
                        status TEXT NOT NULL
                            CHECK (
                                status IN (
                                    'created',
                                    'running',
                                    'completed',
                                    'cancelled',
                                    'failed'
                                )
                            ),
                        created_at TEXT NOT NULL,
                        started_at TEXT,
                        completed_at TEXT,
                        FOREIGN KEY (recipe_id)
                            REFERENCES recipes(id)
                            ON DELETE RESTRICT
                    )
                    """
                )

                connection.execute(
                    """
                    INSERT INTO metadata (key, value)
                    VALUES ('schema_version', '1')
                    """
                )

                recipe_json = (
                    '{"schema_version":1,'
                    '"id":"legacy",'
                    '"name":"Legacy Recipe",'
                    '"stages":[{'
                    '"name":"Hold",'
                    '"duration_minutes":60,'
                    '"temperature_c":25.0,'
                    '"humidity_percent":null'
                    '}]}'
                )

                connection.execute(
                    """
                    INSERT INTO recipes (
                        id, name, recipe_json, updated_at
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        "legacy",
                        "Legacy Recipe",
                        recipe_json,
                        "2026-01-01T00:00:00+00:00",
                    ),
                )

                connection.execute(
                    """
                    INSERT INTO fermentation_runs (
                        id,
                        recipe_id,
                        recipe_snapshot,
                        status,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        "legacy-run",
                        "legacy",
                        recipe_json,
                        "created",
                        "2026-01-01T00:00:00+00:00",
                    ),
                )

    def test_new_database_uses_current_schema(self):
        self.store.initialise()

        self.assertEqual(self.version(), "3")

        with closing(self.connect()) as connection:
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(fermentation_runs)"
                )
            }

        self.assertIn("elapsed_seconds", columns)
        self.assertIn("running_since", columns)
        self.assertIn("paused_at", columns)

    def test_existing_v1_database_migrates(self):
        self.create_v1_database()

        self.store.initialise()

        self.assertEqual(self.version(), "3")

        run = self.store.get_run("legacy-run")

        self.assertEqual(run["status"], "created")
        self.assertEqual(run["elapsed_seconds"], 0)
        self.assertEqual(run["recipe"].id, "legacy")

    def test_current_database_is_idempotent(self):
        self.store.initialise()

        with closing(self.connect()) as connection:
            before = connection.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE name = 'fermentation_runs'"
            ).fetchone()[0]

        self.store.initialise()

        with closing(self.connect()) as connection:
            after = connection.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE name = 'fermentation_runs'"
            ).fetchone()[0]

        self.assertEqual(before, after)
        self.assertEqual(self.version(), "3")

    def test_unsupported_version_rejected(self):
        self.create_v1_database()

        with closing(self.connect()) as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE metadata
                    SET value = '999'
                    WHERE key = 'schema_version'
                    """
                )

        with self.assertRaises(StorageError):
            self.store.initialise()

        self.assertEqual(self.version(), "999")

        with closing(self.connect()) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM fermentation_runs"
            ).fetchone()[0]

        self.assertEqual(count, 1)

    def test_migration_preserves_recipe_snapshot(self):
        self.create_v1_database()

        with closing(self.connect()) as connection:
            before = connection.execute(
                "SELECT recipe_snapshot "
                "FROM fermentation_runs"
            ).fetchone()[0]

        self.store.initialise()

        with closing(self.connect()) as connection:
            after = connection.execute(
                "SELECT recipe_snapshot "
                "FROM fermentation_runs"
            ).fetchone()[0]

        self.assertEqual(before, after)

    def test_repeated_initialisation_preserves_runs(self):
        self.create_v1_database()

        self.store.initialise()
        self.store.initialise()
        self.store.initialise()

        with closing(self.connect()) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM fermentation_runs"
            ).fetchone()[0]

        self.assertEqual(count, 1)
        self.assertEqual(self.version(), "3")


if __name__ == "__main__":
    unittest.main(verbosity=2)
