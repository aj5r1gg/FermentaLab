"""Regression tests for the pre-publication integrity check."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "check-publication.sh"
)


class PublicationCheckTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.root = Path(self.temp.name)

        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "FermentaLab Tests")

        (self.root / "app").mkdir()
        (self.root / "tests").mkdir()

        (self.root / "app" / "baseline.py").write_text(
            "VALUE = 1\n"
        )

        (self.root / "tests" / "test_baseline.py").write_text(
            "import unittest\n"
        )

        self.git("add", ".")
        self.git("commit", "-qm", "Initial baseline")

        self.script = self.root / "check-publication.sh"
        shutil.copy2(SCRIPT, self.script)

    def git(self, *args):
        return subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )

    def check_publication(self):
        return subprocess.run(
            ["bash", str(self.script)],
            cwd=self.root,
            capture_output=True,
            text=True,
        )

    def test_clean_repository_passes(self):
        result = self.check_publication()

        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(
            "PASS: Pre-publication checks completed.",
            result.stdout,
        )

    def test_untracked_application_module_rejected(self):
        (self.root / "app" / "missing.py").write_text(
            "VALUE = 2\n"
        )

        result = self.check_publication()

        self.assertEqual(result.returncode, 1)
        self.assertIn("app/missing.py", result.stdout)

    def test_untracked_test_module_rejected(self):
        (self.root / "tests" / "test_missing.py").write_text(
            "import unittest\n"
        )

        result = self.check_publication()

        self.assertEqual(result.returncode, 1)
        self.assertIn("tests/test_missing.py", result.stdout)

    def test_modified_tracked_module_rejected(self):
        (self.root / "app" / "baseline.py").write_text(
            "VALUE = 99\n"
        )

        result = self.check_publication()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "Uncommitted application or test changes",
            result.stdout,
        )

    def test_staged_uncommitted_change_rejected(self):
        (self.root / "app" / "baseline.py").write_text(
            "VALUE = 99\n"
        )

        self.git("add", "app/baseline.py")

        result = self.check_publication()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "Staged but uncommitted",
            result.stdout,
        )


if __name__ == "__main__":
    unittest.main()
