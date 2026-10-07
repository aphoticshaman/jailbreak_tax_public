import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("release_check", Path(__file__).resolve().parents[1] / "scripts/release_check.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class ReleaseIsolationTests(unittest.TestCase):
    def test_inventory_rejects_traversal_and_private_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("../notes.txt", "private/report.txt", "sources.private.json", "RESEARCH.html", "C:/notes.txt"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    release.checked_files(root, [name])

    def test_inventory_rejects_duplicates_and_missing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "safe.txt").write_text("Invented example", encoding="utf-8")
            self.assertEqual(release.checked_files(root, ["safe.txt"]), [root / "safe.txt"])
            for names in (["safe.txt", "safe.txt"], ["missing.txt"]):
                with self.assertRaises(ValueError):
                    release.checked_files(root, names)

    def test_private_artifact_casing_is_rejected_even_when_file_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("research.html", "Research.html", "WORKSPACE.JSON", "submission-demo.json"):
                (root / name).write_text("Invented private artifact marker", encoding="utf-8")
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "Private artifact"):
                    release.checked_files(root, [name])

    def test_generated_page_detects_external_scripts_and_event_handlers(self):
        page = release.PageData()
        page.feed('<script src="https://example.org/code.js"></script><img onerror="alert(1)">')
        self.assertEqual(len(page.errors), 2)

    def test_credential_pattern_is_detected_without_printing_value(self):
        example = "gh" + "p_" + "a" * 36
        self.assertTrue(any(pattern.search(example) for _, pattern in release.SENSITIVE_PATTERNS))


if __name__ == "__main__":
    unittest.main()
