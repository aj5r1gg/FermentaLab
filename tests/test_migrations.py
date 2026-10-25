"""
FermentaLab schema migration acceptance tests.

All tests use temporary databases.
No persistent application data is modified.
"""

import sqlite3
import tempfile
import unittest

from contextlib import closing
from pathlib import Path

from fermentalab.migrations import (
    MigrationError,
    migrate_v1_to_v2,
)


class TestSchemaMigration(unittest.TestCase):

    def create_legacy_v1_schema(self):
        """Create schema v1 using its original definitions."""
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                connection.execute(
                    'CREATE TABLE IF NOT EXISTS metadata (\n                    key TEXT PRIMARY KEY,\n                    value TEXT NOT NULL\n                )'
                )
                connection.execute(
                    'CREATE TABLE IF NOT EXISTS recipes (\n                    id TEXT PRIMARY KEY,\n                    name TEXT NOT NULL,\n                    recipe_json TEXT NOT NULL,\n                    updated_at TEXT NOT NULL\n                )'
                )
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS fermentation_runs (\n                    id TEXT PRIMARY KEY,\n                    recipe_id TEXT NOT NULL,\n                    recipe_snapshot TEXT NOT NULL,\n                    status TEXT NOT NULL\n                        CHECK (\n                            status IN (\n                                'created',\n                                'running',\n                                'completed',\n                                'cancelled',\n                                'failed'\n                            )\n                        ),\n                    created_at TEXT NOT NULL,\n                    started_at TEXT,\n                    completed_at TEXT,\n                    FOREIGN KEY (recipe_id)\n                        REFERENCES recipes(id)\n                        ON DELETE RESTRICT\n                )"
                )
                connection.execute(
                    "INSERT INTO metadata (key, value) VALUES ('schema_version', '1')"
                )


    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "migration.db"

        self.create_legacy_v1_schema()

        self.connection = sqlite3.connect(self.database)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

        self.connection.execute(
            """
            INSERT INTO recipes (
                id, name, recipe_json, updated_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                "fixture",
                "Migration Fixture",
                '{"schema_version":1,"id":"fixture",'
                '"name":"Migration Fixture","stages":'
                '[{"name":"Hold","duration_minutes":60,'
                '"temperature_c":25.0,'
                '"humidity_percent":null}]}',
                "2026-01-01T00:00:00+00:00",
            ),
        )

        self.connection.execute(
            """
            INSERT INTO fermentation_runs (
                id, recipe_id, recipe_snapshot,
                status, created_at
            )
            SELECT ?, id, recipe_json, ?, ?
            FROM recipes
            WHERE id = ?
            """,
            (
                "run-fixture",
                "created",
                "2026-01-01T00:00:00+00:00",
                "fixture",
            ),
        )

        self.connection.commit()

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def migrate(self):
        migrate_v1_to_v2(self.connection)
        self.connection.commit()

    def test_schema_version_updated(self):
        self.migrate()

        version = self.connection.execute(
            "SELECT value FROM metadata "
            "WHERE key = 'schema_version'"
        ).fetchone()[0]

        self.assertEqual(version, "2")

    def test_recipe_preserved(self):
        before = self.connection.execute(
            "SELECT * FROM recipes WHERE id = 'fixture'"
        ).fetchone()

        self.migrate()

        after = self.connection.execute(
            "SELECT * FROM recipes WHERE id = 'fixture'"
        ).fetchone()

        self.assertEqual(tuple(before), tuple(after))

    def test_run_preserved(self):
        self.migrate()

        row = self.connection.execute(
            "SELECT * FROM fermentation_runs "
            "WHERE id = 'run-fixture'"
        ).fetchone()

        self.assertEqual(row["recipe_id"], "fixture")
        self.assertEqual(row["status"], "created")

    def test_recipe_snapshot_preserved(self):
        before = self.connection.execute(
            "SELECT recipe_snapshot FROM fermentation_runs"
        ).fetchone()[0]

        self.migrate()

        after = self.connection.execute(
            "SELECT recipe_snapshot FROM fermentation_runs"
        ).fetchone()[0]

        self.assertEqual(before, after)

    def test_lifecycle_columns_created(self):
        self.migrate()

        columns = {
            row["name"]
            for row in self.connection.execute(
                "PRAGMA table_info(fermentation_runs)"
            )
        }

        expected = {
            "elapsed_seconds",
            "running_since",
            "paused_at",
            "ended_at",
            "failure_reason",
        }

        self.assertTrue(expected.issubset(columns))

    def test_elapsed_defaults_to_zero(self):
        self.migrate()

        elapsed = self.connection.execute(
            "SELECT elapsed_seconds "
            "FROM fermentation_runs"
        ).fetchone()[0]

        self.assertEqual(elapsed, 0)

    def test_paused_status_accepted(self):
        self.migrate()

        self.connection.execute(
            """
            UPDATE fermentation_runs
            SET status = 'paused'
            WHERE id = 'run-fixture'
            """
        )

        status = self.connection.execute(
            "SELECT status FROM fermentation_runs"
        ).fetchone()[0]

        self.assertEqual(status, "paused")

    def test_unknown_status_rejected(self):
        self.migrate()

        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                UPDATE fermentation_runs
                SET status = 'unknown'
                WHERE id = 'run-fixture'
                """
            )

    def test_negative_elapsed_rejected(self):
        self.migrate()

        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                UPDATE fermentation_runs
                SET elapsed_seconds = -1
                WHERE id = 'run-fixture'
                """
            )

    def test_foreign_keys_preserved(self):
        self.migrate()

        violations = self.connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        self.assertEqual(violations, [])

        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                UPDATE fermentation_runs
                SET recipe_id = 'missing'
                WHERE id = 'run-fixture'
                """
            )

    def test_incompatible_schema_rejected(self):
        self.connection.execute(
            """
            UPDATE metadata
            SET value = '999'
            WHERE key = 'schema_version'
            """
        )
        self.connection.commit()

        with self.assertRaises(MigrationError):
            migrate_v1_to_v2(self.connection)

    def test_migration_is_atomic(self):
        """
        Migration must either complete or leave schema v1 intact.

        This test checks that a rejected migration does not
        modify the original table structure or version.
        """
        self.connection.execute(
            """
            UPDATE metadata
            SET value = '999'
            WHERE key = 'schema_version'
            """
        )
        self.connection.commit()

        before = self.connection.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE name = 'fermentation_runs'"
        ).fetchone()[0]

        with self.assertRaises(MigrationError):
            migrate_v1_to_v2(self.connection)

        after = self.connection.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE name = 'fermentation_runs'"
        ).fetchone()[0]

        self.assertEqual(before, after)


    def test_mid_migration_failure_rolls_back(self):
        """
        Force a failure during data copying.

        The new table must disappear after rollback,
        while the original schema and records survive.
        """
        self.connection.execute(
            """
            ALTER TABLE fermentation_runs
            RENAME COLUMN recipe_snapshot
            TO broken_snapshot
            """
        )
        self.connection.commit()

        original_schema = self.connection.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE name = 'fermentation_runs'
            """
        ).fetchone()[0]

        with self.assertRaises(sqlite3.OperationalError):
            migrate_v1_to_v2(self.connection)

        self.assertFalse(self.connection.in_transaction)

        restored_schema = self.connection.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE name = 'fermentation_runs'
            """
        ).fetchone()[0]

        self.assertEqual(original_schema, restored_schema)

        temporary_table = self.connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE name = 'fermentation_runs_v2'
            """
        ).fetchone()

        self.assertIsNone(temporary_table)

        version = self.connection.execute(
            """
            SELECT value FROM metadata
            WHERE key = 'schema_version'
            """
        ).fetchone()[0]

        self.assertEqual(version, "1")

        run = self.connection.execute(
            """
            SELECT id, status
            FROM fermentation_runs
            WHERE id = 'run-fixture'
            """
        ).fetchone()

        self.assertEqual(run["id"], "run-fixture")
        self.assertEqual(run["status"], "created")

    def test_legacy_running_run_recovered(self):
        """
        A legacy running record must not remain running.

        Historical active time is unknown and must not
        be invented during migration.
        """
        self.connection.execute(
            """
            UPDATE fermentation_runs
            SET status = 'running',
                started_at = ?
            WHERE id = 'run-fixture'
            """,
            ("2026-01-01T01:00:00+00:00",),
        )
        self.connection.commit()

        self.migrate()

        row = self.connection.execute(
            """
            SELECT status,
                   started_at,
                   elapsed_seconds,
                   running_since,
                   failure_reason
            FROM fermentation_runs
            WHERE id = 'run-fixture'
            """
        ).fetchone()

        self.assertEqual(row["status"], "paused")
        self.assertEqual(
            row["started_at"],
            "2026-01-01T01:00:00+00:00",
        )
        self.assertEqual(row["elapsed_seconds"], 0)
        self.assertIsNone(row["running_since"])
        self.assertIn(
            "elapsed time unknown",
            row["failure_reason"],
        )

    def test_foreign_keys_disabled_rejected(self):
        """
        Migration must refuse connections without
        foreign-key enforcement.
        """
        self.connection.execute(
            "PRAGMA foreign_keys = OFF"
        )

        with self.assertRaises(MigrationError):
            migrate_v1_to_v2(self.connection)

        version = self.connection.execute(
            """
            SELECT value FROM metadata
            WHERE key = 'schema_version'
            """
        ).fetchone()[0]

        self.assertEqual(version, "1")

    def test_active_transaction_rejected(self):
        """
        Migration must not take ownership of a
        transaction started by its caller.
        """
        self.connection.execute("BEGIN")

        with self.assertRaises(MigrationError):
            migrate_v1_to_v2(self.connection)

        self.assertTrue(self.connection.in_transaction)

        self.connection.rollback()

        version = self.connection.execute(
            """
            SELECT value FROM metadata
            WHERE key = 'schema_version'
            """
        ).fetchone()[0]

        self.assertEqual(version, "1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
