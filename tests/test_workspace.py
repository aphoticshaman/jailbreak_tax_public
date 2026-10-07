"""Metadata, provenance, isolation, and rendering tests using invented inputs."""
from __future__ import annotations

from contextlib import contextmanager
import copy
import ctypes
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build
from scripts import workspace as ws


def export(sid="fictional-one", length=2, accepted=False):
    return {"submissionId": sid, "challenge": "Fictional challenge", "chatId": "fictional-chat", "scenario": "Fictional scheduling policy",
            "model": "Fictional model", "status": "accepted" if accepted else "rejected", "submittedAt": "2025-01-01T12:30:00Z" if length == 2 else "2025-01-01T13:30:00Z",
            "title": "PRIVATE_TITLE_NOT_FOR_IMPORT", "judge": {"isBreak": accepted, "criteria": [{"name": "Fictional criterion", "score": 8 if accepted else 0}]},
            "messages": [{"role": "user" if i % 2 == 0 else "assistant", "content": "PRIVATE_TRANSCRIPT_NOT_FOR_IMPORT " + str(i), "timestamp": "2025-01-01T12:%02d:00Z" % i} for i in range(length)]}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ws.encoded(value))
    return path


class DataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = None
        self.blocks = {}

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "script" and values.get("id") in {"catalog-data", "workspace-data"}:
            self.active = values["id"]
            self.blocks[self.active] = ""

    def handle_data(self, data):
        if self.active:
            self.blocks[self.active] += data

    def handle_endtag(self, tag):
        if tag == "script":
            self.active = None


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.private = self.base / "private"
        self.source = self.base / "exports"
        ws.init(self.private, "Fictional private study")

    def state(self):
        return {name: (self.private / name).read_bytes() for name in ws.FILES}

    def seed(self):
        first = write(self.source / "first.json", export())
        second = write(self.source / "second.json", export("fictional-two", 4, True))
        originals = {p: p.read_bytes() for p in (first, second)}
        result = ws.ingest(self.private, self.source)
        return result, originals

    def card(self):
        records = ws.read_json(self.private / "workspace.json")["records"]
        return {"id": "fictional-card", "title": "A bounded observation", "kind": "observation", "statement": "The invented labels differ.",
                "evidence_refs": [records[0]["id"]], "taxonomy_ids": [], "alternative_explanations": ["A different criterion scope could matter."],
                "next_check": "Inspect the criterion definition.", "source_urls": ["https://example.org/method"], "status": "supported", "novelty": "not-assessed"}

    def test_counts_prefixes_preservation_and_no_transcript_storage(self):
        result, originals = self.seed()
        self.assertEqual(result["summary"], dict(submission_count=2, chat_count=1, accepted_submissions=1, accepted_cells=1, source_count=2, messages_snapshot=6, messages_distinct=4))
        snapshots = ws.read_json(self.private / "snapshots.private.json")
        self.assertTrue(snapshots["chains"][0]["strict_prefix"])
        for path, raw in originals.items():
            self.assertEqual(path.read_bytes(), raw)
        for raw in self.state().values():
            self.assertNotIn(b"PRIVATE_TRANSCRIPT_NOT_FOR_IMPORT", raw)
            self.assertNotIn(b"PRIVATE_TITLE_NOT_FOR_IMPORT", raw)
        private_index = ws.read_json(self.private / "sources.private.json")
        self.assertEqual({v["sha256"] for v in private_index["records"].values()}, {hashlib.sha256(raw).hexdigest() for raw in originals.values()})

    def test_duplicate_copies_and_reingest_are_idempotent(self):
        self.seed()
        (self.source / "submission-copy.txt").write_bytes((self.source / "first.json").read_bytes())
        result = ws.ingest(self.private, self.source)
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["summary"]["source_count"], 2)
        before = self.state()
        self.assertFalse(ws.ingest(self.private, self.source)["changed"])
        self.assertEqual(before, self.state())

    def test_conflicting_submission_aborts_whole_import(self):
        self.seed()
        before = self.state()
        conflicting = export()
        conflicting["model"] = "Different fictional model"
        write(self.source / "conflict.json", conflicting)
        write(self.source / "new.json", export("fictional-new"))
        with self.assertRaises(ws.WorkspaceError):
            ws.ingest(self.private, self.source)
        self.assertEqual(before, self.state())

    def test_malformed_json_and_duplicate_keys_preserve_state(self):
        self.seed()
        before = self.state()
        for raw in (b'{"submissionId":', b'{"submissionId":"a","submissionId":"b"}'):
            (self.source / "malformed.json").write_bytes(raw)
            with self.assertRaises(ws.WorkspaceError):
                ws.ingest(self.private, self.source)
            self.assertEqual(before, self.state())

    def test_timestamp_and_tool_call_shape_validation(self):
        for calls in ({}, False, "", [{}]):
            value = export()
            value["messages"][0]["toolCalls"] = calls
            with self.subTest(calls=calls), self.assertRaises(ws.WorkspaceError):
                ws.extract(value, ws.encoded(value), value["challenge"])
        value = export()
        value["messages"][0]["timestamp"] = "2025-01-01T12:00:00"
        with self.assertRaises(ws.WorkspaceError):
            ws.extract(value, ws.encoded(value), value["challenge"])

    def test_renamed_export_tree_and_manifest_missing_files(self):
        value = export()
        value.pop("challenge")
        write(self.source / "submission-fictional.txt", value)
        manifest = {"challenge": {"slug": "Fictional challenge"}, "files": [{"file": "submission-fictional.json", "id": value["submissionId"]}]}
        write(self.source / "manifest.txt", manifest)
        self.assertEqual(ws.ingest(self.private, self.source)["added"], 1)
        before = self.state()
        manifest["files"].append({"file": "missing.json", "id": "fictional-missing"})
        write(self.source / "manifest.txt", manifest)
        with self.assertRaises(ws.WorkspaceError):
            ws.ingest(self.private, self.source)
        self.assertEqual(before, self.state())
        self.assertTrue(ws.ingest(self.private, self.source / "submission-fictional.txt")["warnings"])
        self.assertTrue(ws.check(self.private)["warnings"])

    def test_source_metadata_is_parsed_from_the_hashed_read(self):
        file = write(self.source / "first.json", export())
        original = Path.read_bytes
        reads = []
        def track(path):
            if path == file:
                reads.append(path)
            return original(path)
        with patch.object(Path, "read_bytes", track):
            ws.ingest(self.private, file)
        self.assertEqual(len(reads), 1)

    def test_invalid_references_supported_kind_and_card_revisions(self):
        self.seed()
        card = self.card()
        file = write(self.base / "card.json", card)
        ws.add(self.private, file)
        before = self.state()
        for update in ({"evidence_refs": ["unknown"]}, {"taxonomy_ids": ["unknown"]}, {"kind": "hypothesis"}, {"source_urls": ["javascript:alert(1)"]}):
            write(file, {**card, **update})
            with self.subTest(update=update), self.assertRaises(ws.WorkspaceError):
                ws.add(self.private, file, replace=True)
            self.assertEqual(before, self.state())
        revised = {**card, "statement": "The interpretation has been corrected."}
        write(file, revised)
        with self.assertRaises(ws.WorkspaceError):
            ws.add(self.private, file)
        self.assertTrue(ws.add(self.private, file, replace=True)["changed"])
        history = ws.read_json(self.private / "sources.private.json")["card_history"]
        self.assertEqual(history[card["id"]][0]["card"], card)
        self.assertFalse(ws.add(self.private, file, replace=True)["changed"])

    def test_failed_bundle_write_rolls_back_and_preserves_cards(self):
        self.seed()
        before = self.state()
        original = ws.atomic_write
        failed = []
        def fail_once(path, content):
            if path.name == "sources.private.json" and not failed:
                failed.append(True)
                raise OSError("Invented write failure")
            return original(path, content)
        file = write(self.base / "card.json", self.card())
        with patch.object(ws, "atomic_write", fail_once), self.assertRaises(OSError):
            ws.add(self.private, file)
        self.assertEqual(before, self.state())
        self.assertFalse((self.private / ".jt-transaction.json").exists())

    def test_isolation_and_init_no_overwrite(self):
        for path in (ws.ROOT, ws.ROOT / "private", ws.ROOT.parent):
            with self.subTest(path=path), self.assertRaises(ws.WorkspaceError):
                ws.workspace_path(path)
        before = self.state()
        with self.assertRaises(ws.WorkspaceError):
            ws.init(self.private, "Replacement")
        self.assertEqual(before, self.state())

    @unittest.skipUnless(os.name == "nt", "Windows alias test")
    def test_windows_extended_namespace_and_short_alias_isolation(self):
        with self.assertRaises(ws.WorkspaceError):
            ws.workspace_path("\\\\?\\" + str(ws.ROOT))
        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetShortPathNameW(str(ws.ROOT), buffer, len(buffer))
        self.assertGreater(length, 0)
        with self.assertRaises(ws.WorkspaceError):
            ws.workspace_path(buffer.value)
        with self.assertRaises(ws.WorkspaceError):
            ws.workspace_path(str(Path(buffer.value) / "new-private"))

    def test_symbolic_link_paths_rejected(self):
        link = self.base / "linked"
        try:
            link.symlink_to(self.private, target_is_directory=True)
        except OSError:
            self.skipTest("This host does not permit creation of symbolic links")
        with self.assertRaises(ws.WorkspaceError):
            ws.workspace_path(link)

    def test_init_rechecks_after_lock_acquisition(self):
        new = self.base / "racing"
        original = ws.locked
        @contextmanager
        def intervening(path):
            with original(path):
                (path / "workspace.json").write_bytes(b"preserve this concurrent result")
                yield
        with patch.object(ws, "locked", intervening), self.assertRaises(ws.WorkspaceError):
            ws.init(new, "Unexpected overwrite")
        self.assertEqual((new / "workspace.json").read_bytes(), b"preserve this concurrent result")

    def test_brief_has_metadata_but_no_source_paths(self):
        self.seed()
        result = ws.brief(self.private)
        self.assertEqual(len(result["records"]), 2)
        self.assertNotIn(str(self.source), json.dumps(result))
        self.assertNotIn("PRIVATE_TRANSCRIPT_NOT_FOR_IMPORT", json.dumps(result))

    def test_ambiguous_nonprefix_is_reported(self):
        self.seed()
        value = export("fictional-third", 4)
        value["messages"][0]["content"] = "A different invented opening"
        value["submittedAt"] = "2025-01-01T14:00:00Z"
        write(self.source / "third.json", value)
        result = ws.ingest(self.private, self.source)
        self.assertTrue(result["warnings"])


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ("web/index.html", "web/style.css", "web/app.js", "data/catalog.json", "examples/demo-workspace.json"):
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ws.ROOT / name).read_bytes())

    def test_literal_script_data_and_markers_roundtrip_safely(self):
        catalog = ws.read_json(self.root / "data/catalog.json")
        demo = ws.read_json(self.root / "examples/demo-workspace.json")
        dangerous = '</script><script id="unwanted">alert(1)</script>& CATALOG_JSON WORKSPACE_JSON'
        demo["title"] = dangerous
        rendered = build.render(self.root, catalog, demo).decode("utf-8")
        self.assertNotIn(dangerous, rendered)
        self.assertNotIn('<script id="unwanted">', rendered)
        parser = DataParser()
        parser.feed(rendered)
        self.assertEqual(json.loads(parser.blocks["workspace-data"])["title"], dangerous)
        self.assertEqual(json.loads(parser.blocks["catalog-data"]), catalog)

    def test_public_build_is_deterministic_fixed_input_and_rejects_private(self):
        write(self.root / "private-temptation.json", {"secret": "NEVER_IMPORT_THIS"})
        build.build_public(self.root)
        before = (self.root / "START.html").read_bytes()
        self.assertNotIn(b"NEVER_IMPORT_THIS", before)
        self.assertEqual(before, (self.root / "index.html").read_bytes())
        build.build_public(self.root)
        self.assertEqual(before, (self.root / "START.html").read_bytes())
        demo = ws.read_json(self.root / "examples/demo-workspace.json")
        demo["visibility"] = "private"
        write(self.root / "examples/demo-workspace.json", demo)
        with self.assertRaises(ws.WorkspaceError):
            build.build_public(self.root)
        self.assertEqual(before, (self.root / "START.html").read_bytes())

    def test_unknown_catalog_fields_fail_without_overwriting_outputs(self):
        build.build_public(self.root)
        before = (self.root / "START.html").read_bytes()
        catalog = ws.read_json(self.root / "data/catalog.json")
        catalog["private_extra"] = "not a reviewed public field"
        write(self.root / "data/catalog.json", catalog)
        with self.assertRaises(ws.WorkspaceError):
            build.build_public(self.root)
        self.assertEqual(before, (self.root / "START.html").read_bytes())


if __name__ == "__main__":
    unittest.main()
