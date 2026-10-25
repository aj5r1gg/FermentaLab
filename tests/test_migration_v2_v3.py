"""Acceptance tests for schema v2 to v3 migration."""

import sqlite3
import tempfile
import unittest

from contextlib import closing
from pathlib import Path

from fermentalab.recipes import Recipe
from fermentalab.storage import RecipeStore


class TestMigrationV2ToV3(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.database = (
            Path(self.temp.name) / "fermentalab.db"
        )

        # Construct a historical v2 database independently
        # of the future v3 initialisation path.
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("PRAGMA foreign_keys = ON")

            db.executescript("""
                CREATE TABLE metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE recipes (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    recipe_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE fermentation_runs (
                    id TEXT PRIMARY KEY,
                    recipe_id TEXT NOT NULL,
                    recipe_snapshot TEXT NOT NULL,
                    status TEXT NOT NULL
                        CHECK (
                            status IN (
                                'created',
                                'running',
                                'paused',
                                'completed',
                                'cancelled',
                                'failed'
                            )
                        ),
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    elapsed_seconds INTEGER NOT NULL DEFAULT 0
                        CHECK (elapsed_seconds >= 0),
                    running_since TEXT,
                    paused_at TEXT,
                    ended_at TEXT,
                    failure_reason TEXT,
                    FOREIGN KEY (recipe_id)
                        REFERENCES recipes(id)
                        ON DELETE RESTRICT
                );
            """)

            db.execute(
                """
                INSERT INTO metadata (key, value)
                VALUES ('schema_version', '2')
                """
            )

            recipe_json = (
                '{"schema_version":1,'
                '"id":"migration-fixture",'
                '"name":"Migration Fixture",'
                '"stages":[{'
                '"name":"Incubation",'
                '"duration_minutes":120,'
                '"temperature_c":35.0,'
                '"humidity_percent":null'
                '}]}'
            )

            db.execute(
                """
                INSERT INTO recipes (
                    id, name, recipe_json, updated_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    "migration-fixture",
                    "Migration Fixture",
                    recipe_json,
                    "2026-10-25T10:00:00+00:00",
                ),
            )

            db.execute(
                """
                INSERT INTO fermentation_runs (
                    id,
                    recipe_id,
                    recipe_snapshot,
                    status,
                    created_at,
                    started_at,
                    elapsed_seconds,
                    running_since,
                    paused_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "migration-run",
                    "migration-fixture",
                    recipe_json,
                    "paused",
                    "2026-10-25T10:00:00+00:00",
                    "2026-10-25T10:01:00+00:00",
                    125,
                    None,
                    "2026-10-25T10:03:05+00:00",
                ),
            )

            db.commit()

        self.store = RecipeStore(self.database)

    def test_v2_database_migrates_to_v3(self):
        self.store.initialise()

        with closing(sqlite3.connect(self.database)) as db:
            version = db.execute(
                """
                SELECT value FROM metadata
                WHERE key = 'schema_version'
                """
            ).fetchone()[0]

        self.assertEqual(version, "3")

    def test_elapsed_seconds_preserved(self):
        self.store.initialise()

        run = self.store.get_run("migration-run")

        self.assertEqual(run["elapsed_seconds"], 125)

    def test_elapsed_microseconds_converted(self):
        self.store.initialise()

        run = self.store.get_run("migration-run")

        self.assertEqual(
            run["elapsed_microseconds"],
            125_000_000,
        )

    def test_run_status_preserved(self):
        self.store.initialise()

        run = self.store.get_run("migration-run")

        self.assertEqual(run["status"], "paused")

    def test_run_timestamps_preserved(self):
        self.store.initialise()

        run = self.store.get_run("migration-run")

        self.assertEqual(
            run["started_at"],
            "2026-10-25T10:01:00+00:00",
        )

        self.assertEqual(
            run["paused_at"],
            "2026-10-25T10:03:05+00:00",
        )

    def test_recipe_snapshot_preserved(self):
        self.store.initialise()

        run = self.store.get_run("migration-run")

        self.assertEqual(
            run["recipe"].id,
            "migration-fixture",
        )

        self.assertEqual(
            run["recipe"].total_duration_minutes,
            120,
        )

    def test_foreign_keys_remain_valid(self):
        self.store.initialise()

        with closing(sqlite3.connect(self.database)) as db:
            violations = db.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()

        self.assertEqual(violations, [])

    def test_database_integrity(self):
        self.store.initialise()

        with closing(sqlite3.connect(self.database)) as db:
            result = db.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]

        self.assertEqual(result, "ok")

    def test_repeated_initialisation_preserves_data(self):
        self.store.initialise()
        self.store.initialise()

        run = self.store.get_run("migration-run")

        self.assertEqual(run["elapsed_seconds"], 125)
        self.assertEqual(
            run["elapsed_microseconds"],
            125_000_000,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
