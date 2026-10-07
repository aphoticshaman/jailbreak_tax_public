import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("check_catalog", ROOT / "scripts/check_catalog.py")
catalog_checks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(catalog_checks)


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads((ROOT / "data/catalog.json").read_text(encoding="utf-8"))

    def modified(self):
        return copy.deepcopy(self.catalog)

    def test_public_catalog_references_and_shape(self):
        self.assertEqual(catalog_checks.validate_catalog(self.catalog), [])
        self.assertEqual(len(self.catalog["entries"]), 65)
        self.assertEqual(len(self.catalog["categories"]), 16)
        self.assertEqual(len(self.catalog["evaluation_dimensions"]), 8)
        self.assertEqual(len({entry["summary"] for entry in self.catalog["entries"]}), 65)

    def test_unknown_fields_cannot_silently_import_other_data(self):
        for where, key in ((None, "records"), ("entries", "practical_guide"), ("sources", "source_path")):
            data = self.modified()
            target = data if where is None else data[where][0]
            target[key] = "Invented extra field"
            with self.subTest(where=where):
                self.assertTrue(any("unknown" in error for error in catalog_checks.validate_catalog(data)))

    def test_unresolved_references_are_rejected(self):
        for field in ("category_id", "source_ids", "related_ids"):
            data = self.modified()
            data["entries"][0][field] = "missing" if field == "category_id" else ["missing"]
            with self.subTest(field=field):
                self.assertTrue(catalog_checks.validate_catalog(data))
        data = self.modified()
        data["learning_paths"][0]["entry_ids"] = ["missing"]
        self.assertTrue(catalog_checks.validate_catalog(data))

    def test_duplicate_identifiers_and_wrong_categories_are_rejected(self):
        data = self.modified()
        data["entries"][1]["id"] = data["entries"][0]["id"]
        self.assertTrue(any("duplicate identifier" in error for error in catalog_checks.validate_catalog(data)))
        data = self.modified()
        data["entries"][0]["category_id"] = data["categories"][1]["id"]
        self.assertTrue(any("does not match" in error for error in catalog_checks.validate_catalog(data)))

    def test_source_links_require_public_https(self):
        bad = ["http://example.org/paper", "javascript:void(0)", "file:///example.txt", "https://name:password@example.org/paper", "https://localhost/paper", "https://127.0.0.1/paper", "https://[::1]/paper", "https://example.org:8443/paper", "https://example.org\\paper", "https://example.org/\npage"]
        for value in bad:
            with self.subTest(value=value):
                self.assertFalse(catalog_checks.valid_https(value))
        self.assertTrue(catalog_checks.valid_https("https://example.org/paper?id=fictional"))

    def test_source_review_and_calendar_dates_are_required(self):
        for field, value in (("review_depth", ""), ("scope_note", None), ("reviewed_on", "2026-02-31"), ("year", True)):
            data = self.modified()
            data["sources"][0][field] = value
            with self.subTest(field=field):
                self.assertTrue(catalog_checks.validate_catalog(data))

    def test_malformed_records_fail_without_crashing(self):
        variants = [None, [], {}, {**self.catalog, "schema_version": True}]
        data = self.modified()
        data["entries"][0]["category_id"] = {"invented": "value"}
        variants.append(data)
        data = self.modified()
        data["entries"][0]["source_ids"] = [{"invented": "value"}]
        variants.append(data)
        for data in variants:
            with self.subTest(kind=type(data).__name__):
                self.assertTrue(catalog_checks.validate_catalog(data))


if __name__ == "__main__":
    unittest.main()
