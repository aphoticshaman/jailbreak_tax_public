"""Offline metadata bookkeeping. Private source content is never persisted."""
from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
FILES = ("workspace.json", "sources.private.json", "snapshots.private.json")
SUMMARY_KEYS = ("submission_count", "chat_count", "accepted_submissions", "accepted_cells", "source_count", "messages_snapshot", "messages_distinct")


class WorkspaceError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise WorkspaceError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def parse_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON object key")
            result[key] = value
        return result
    try:
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(WorkspaceError("Non-finite JSON number")))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise WorkspaceError("Invalid UTF-8 JSON input") from error


def read_json(path):
    return parse_json(path.read_bytes())


def safe_path(path):
    """Refuse symbolic links, Windows junctions, and every other reparse point."""
    path = Path(os.path.abspath(os.path.expanduser(str(path))))
    require(not str(path).startswith(("\\\\?\\", "\\\\.\\")), "Windows device namespace paths are not supported")
    for part in reversed((path, *path.parents)):
        if os.path.lexists(part):
            details = os.lstat(part)
            require(not stat.S_ISLNK(details.st_mode) and not (getattr(details, "st_file_attributes", 0) & 0x400),
                    "Linked or reparse-point paths are not supported")
    # resolve normalizes existing Windows 8.3 aliases as well as dot components.
    return path.resolve()


def workspace_path(path, root=None):
    path = safe_path(path)
    public = safe_path(root or ROOT)
    require(not path.is_relative_to(public) and not public.is_relative_to(path),
            "Private workspace must be outside and not an ancestor of the public repository")
    return path


def https_url(value):
    if not isinstance(value, str) or any(ord(c) <= 32 for c in value) or "\\" in value:
        return False
    try:
        p = urlsplit(value)
        return p.scheme == "https" and bool(p.hostname) and not p.username and not p.password and p.port in (None, 443)
    except ValueError:
        return False


def text(value, label, allow_empty=False):
    require(isinstance(value, str) and (allow_empty or bool(value.strip())), label + " must be a string")
    return value


def strings(value, label):
    require(isinstance(value, list) and all(isinstance(v, str) for v in value), label + " must be an array of strings")


def timestamp(value):
    text(value, "Timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise WorkspaceError("Invalid timestamp") from error
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None, "Timestamp must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def count(value, label):
    require(type(value) is int and value >= 0, label + " must be a nonnegative integer")


def criteria(value):
    require(isinstance(value, list), "Criteria must be a list")
    seen = set()
    for item in value:
        require(isinstance(item, dict) and set(item) == {"name", "score"}, "Criterion needs only name and score")
        text(item["name"], "Criterion name")
        require(item["name"] not in seen, "Duplicate criterion name")
        seen.add(item["name"])
        score = item["score"]
        require(type(score) in (int, float) and math.isfinite(score), "Criterion score must be finite numeric data")


def validate_card(card, record_ids, taxonomy_ids):
    fields = {"id", "title", "kind", "statement", "evidence_refs", "taxonomy_ids", "alternative_explanations", "next_check", "source_urls", "status", "novelty"}
    require(isinstance(card, dict) and set(card) == fields, "Card fields must match the product contract")
    for key in ("id", "title", "statement", "next_check"):
        text(card[key], "Card " + key)
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", card["id"]) is not None, "Invalid card ID")
    require(card["kind"] in {"observation", "hypothesis", "question"}, "Invalid card kind")
    require(card["status"] in {"proposed", "supported", "contested", "unresolved"}, "Invalid card status")
    require(card["novelty"] in {"not-assessed", "prior-art-required"}, "Novelty cannot be automatically asserted")
    for key in ("evidence_refs", "taxonomy_ids", "alternative_explanations", "source_urls"):
        strings(card[key], key)
    require(set(card["evidence_refs"]) <= record_ids, "Card contains unknown evidence references")
    require(set(card["taxonomy_ids"]) <= taxonomy_ids, "Card contains unknown taxonomy references")
    require(all(https_url(url) for url in card["source_urls"]), "Card links must be credential-free HTTPS URLs")
    require(card["status"] != "supported" or (card["kind"] == "observation" and bool(card["evidence_refs"])), "Supported cards must be observations with recorded evidence")


def validate_workspace(data, taxonomy_ids):
    fields = {"schema_version", "visibility", "title", "selection_note", "limitations", "summary", "records", "cards"}
    require(isinstance(data, dict) and set(data) == fields and type(data["schema_version"]) is int and data["schema_version"] == 1, "Invalid workspace schema")
    require(data["visibility"] in {"private", "demo"}, "Invalid workspace visibility")
    text(data["title"], "Workspace title")
    text(data["selection_note"], "Selection note")
    strings(data["limitations"], "Limitations")
    require(isinstance(data["summary"], dict) and set(data["summary"]) == set(SUMMARY_KEYS), "Invalid summary fields")
    for key, value in data["summary"].items():
        count(value, key)
    require(isinstance(data["records"], list) and isinstance(data["cards"], list), "Records and cards must be lists")
    ids = set()
    record_fields = {"id", "challenge", "scenario", "model", "submitted_at", "platform_status", "chat_id", "message_count", "tool_call_count", "evidence_level", "source_sha256", "criteria"}
    for record in data["records"]:
        require(isinstance(record, dict) and set(record) == record_fields, "Invalid record fields")
        for key in record_fields - {"message_count", "tool_call_count", "criteria"}:
            text(record[key], "Record " + key)
        require(record["id"] not in ids, "Duplicate record ID")
        ids.add(record["id"])
        require(re.fullmatch(r"[a-f0-9]{64}", record["source_sha256"]) is not None, "Invalid source SHA256")
        timestamp(record["submitted_at"])
        count(record["message_count"], "Message count")
        count(record["tool_call_count"], "Tool-call count")
        criteria(record["criteria"])
    card_ids = set()
    for card in data["cards"]:
        validate_card(card, ids, taxonomy_ids)
        require(card["id"] not in card_ids, "Duplicate card ID")
        card_ids.add(card["id"])
    records = data["records"]
    accepted = [r for r in records if r["platform_status"] == "accepted"]
    computed = {"submission_count": len(records), "chat_count": len({(r["challenge"], r["chat_id"]) for r in records}),
                "accepted_submissions": len(accepted), "accepted_cells": len({(r["challenge"], r["scenario"], r["model"]) for r in accepted}),
                "source_count": len({r["source_sha256"] for r in records}), "messages_snapshot": sum(r["message_count"] for r in records)}
    require(all(data["summary"][k] == v for k, v in computed.items()), "Summary does not match records")
    require(data["summary"]["messages_distinct"] <= data["summary"]["messages_snapshot"], "Distinct messages exceed snapshot messages")
    return data


def taxonomy_ids(root=None):
    path = safe_path((root or ROOT) / "data" / "catalog.json")
    catalog = read_json(path)
    return {item["id"] for item in catalog["entries"]}


def atomic_write(path, content):
    safe_path(path)
    fd, temp = tempfile.mkstemp(prefix=".jt-write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def recover(path):
    journal = safe_path(path / ".jt-transaction.json")
    if not journal.exists():
        return
    data = read_json(journal)
    require(isinstance(data, dict) and set(data) == {"before"} and isinstance(data["before"], dict)
            and set(data["before"]) == set(FILES), "Invalid transaction journal; manual inspection required")
    decoded = {}
    for name, value in data["before"].items():
        require(value is None or isinstance(value, str), "Invalid transaction backup")
        try:
            decoded[name] = None if value is None else base64.b64decode(value, validate=True)
        except ValueError as error:
            raise WorkspaceError("Invalid transaction backup") from error
    for name, content in decoded.items():
        destination = safe_path(path / name)
        if content is None:
            destination.unlink(missing_ok=True)
        else:
            atomic_write(destination, content)
    journal.unlink()


@contextmanager
def locked(path):
    require(path.is_dir(), "Workspace directory does not exist; run init first")
    lock = safe_path(path / ".jt.lock")
    with open(lock, "a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise WorkspaceError("Workspace is in use by another process") from error
        try:
            recover(path)
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def commit(path, workspace, sources, snapshots):
    proposed = dict(zip(FILES, map(encoded, (workspace, sources, snapshots))))
    previous = {name: safe_path(path / name).read_bytes() if (path / name).exists() else None for name in FILES}
    if proposed == previous:
        return False
    journal = path / ".jt-transaction.json"
    atomic_write(journal, encoded({"before": {name: None if value is None else base64.b64encode(value).decode("ascii") for name, value in previous.items()}}))
    try:
        for name, content in proposed.items():
            atomic_write(path / name, content)
        journal.unlink()
    except BaseException:
        recover(path)
        raise
    return True


def recompute(workspace, snapshots):
    records = workspace["records"]
    accepted = [r for r in records if r["platform_status"] == "accepted"]
    events = {(r["challenge"], r["chat_id"], msg) for r in records for msg in snapshots["records"][r["id"]]["message_hashes"]}
    workspace["summary"] = {"submission_count": len(records), "chat_count": len({(r["challenge"], r["chat_id"]) for r in records}),
                            "accepted_submissions": len(accepted), "accepted_cells": len({(r["challenge"], r["scenario"], r["model"]) for r in accepted}),
                            "source_count": len({r["source_sha256"] for r in records}), "messages_snapshot": sum(r["message_count"] for r in records), "messages_distinct": len(events)}
    groups = {}
    for r in records:
        groups.setdefault((r["challenge"], r["chat_id"]), []).append(r)
    chains, warnings = [], []
    for group in groups.values():
        group.sort(key=lambda r: (timestamp(r["submitted_at"]), r["id"]))
        for before, after in zip(group, group[1:]):
            a = snapshots["records"][before["id"]]["message_hashes"]
            b = snapshots["records"][after["id"]]["message_hashes"]
            prefix = len(a) < len(b) and a == b[:len(a)]
            equal_time = timestamp(before["submitted_at"]) == timestamp(after["submitted_at"])
            chains.append({"previous": before["id"], "next": after["id"], "strict_prefix": prefix and not equal_time,
                           "identical_snapshot": a == b, "ambiguous_order": equal_time, "previous_messages": len(a), "next_messages": len(b)})
            if equal_time or (not prefix and a != b):
                warnings.append({"kind": "ambiguous_snapshot_relationship", "refs": [before["id"], after["id"]]})
    snapshots["chains"] = chains
    snapshots["warnings"] = warnings


def load(path):
    workspace, sources, snapshots = [read_json(safe_path(path / name)) for name in FILES]
    validate_workspace(workspace, taxonomy_ids())
    require(workspace["visibility"] == "private", "CLI operations require a private workspace")
    ids = {r["id"] for r in workspace["records"]}
    require(isinstance(sources, dict) and sources.get("schema_version") == 1 and isinstance(sources.get("records"), dict), "Invalid private source index")
    require(isinstance(snapshots, dict) and snapshots.get("schema_version") == 1 and isinstance(snapshots.get("records"), dict), "Invalid private snapshot index")
    require(set(sources["records"]) == ids == set(snapshots["records"]), "Private indexes do not match workspace records")
    for record in workspace["records"]:
        source = sources["records"][record["id"]]
        snapshot = snapshots["records"][record["id"]]
        require(source.get("sha256") == record["source_sha256"] and isinstance(source.get("submission_id"), str), "Source identity mismatch")
        strings(source.get("paths"), "Private source paths")
        hashes = snapshot.get("message_hashes")
        require(isinstance(hashes, list) and len(hashes) == record["message_count"] and all(isinstance(h, str) and re.fullmatch(r"[a-f0-9]{64}", h) for h in hashes), "Invalid message hash index")
    original = canonical(workspace["summary"])
    recompute(workspace, snapshots)
    require(canonical(workspace["summary"]) == original, "Private message index disagrees with workspace summary")
    return workspace, sources, snapshots


def init(path, name):
    path = workspace_path(path)
    text(name, "Workspace name")
    if path.exists():
        require(path.is_dir() and not any(path.iterdir()), "Init requires a new or empty private directory")
    else:
        path.mkdir(parents=True)
    workspace = {"schema_version": 1, "visibility": "private", "title": name,
                 "selection_note": "Imported records describe supplied submissions; completeness and selection require an operator account.",
                 "limitations": ["Platform judgments are measurements at export, not independent verification of success.", "Chat counts and submission counts are not attack-attempt denominators.", "Authorship, unseen feedback, hidden state, and causal effects remain unknown unless separately evidenced."],
                 "summary": dict.fromkeys(SUMMARY_KEYS, 0), "records": [], "cards": []}
    with locked(path):
        require(not any(p.name != ".jt.lock" for p in path.iterdir()), "Workspace changed during initialization; refusing to overwrite it")
        commit(path, workspace, {"schema_version": 1, "records": {}}, {"schema_version": 1, "records": {}, "chains": [], "warnings": []})
    return {"workspace": str(path), "created": True}


def challenge_name(value):
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, dict):
        for key in ("slug", "id"):
            if isinstance(value.get(key), str) and value[key].strip():
                return value[key]
    return None


def candidates(source):
    source = safe_path(source)
    require(source.exists(), "Source does not exist")
    paths, ignored = [], 0
    if source.is_file():
        paths = [source]
    else:
        require(source.is_dir(), "Source must be a file or directory")
        for directory, dirs, names in os.walk(source, followlinks=False):
            for name in dirs:
                safe_path(Path(directory) / name)
            for name in names:
                path = safe_path(Path(directory) / name)
                if path.suffix.lower() in {".json", ".txt"}:
                    paths.append(path)
                else:
                    ignored += 1
    manifests = {}
    pending = []
    for path in sorted(paths):
        raw = path.read_bytes()
        if path.suffix.lower() == ".txt" and not path.name.lower().startswith("submission-") and not raw.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"{"):
            ignored += 1
            continue
        data = parse_json(raw)
        if path.name.lower() in {"manifest.json", "manifest.txt"}:
            require(isinstance(data, dict) and isinstance(data.get("files"), list) and challenge_name(data.get("challenge")), "Malformed export manifest")
            require(path.parent not in manifests or manifests[path.parent] == data, "Conflicting manifests in one directory")
            manifests[path.parent] = data
        else:
            require(isinstance(data, dict) and "submissionId" in data, "Non-export JSON encountered; choose a directory containing supported exports")
            pending.append((path, raw, data))
    require(bool(pending), "No supported submission exports found")
    for path, raw, data in pending:
        if path.parent not in manifests:
            for name in ("manifest.json", "manifest.txt"):
                neighbor = safe_path(path.parent / name)
                if neighbor.is_file():
                    m = read_json(neighbor)
                    require(isinstance(m, dict) and challenge_name(m.get("challenge")) and isinstance(m.get("files"), list), "Malformed neighboring manifest")
                    require(path.parent not in manifests or manifests[path.parent] == m, "Conflicting neighboring manifests")
                    manifests[path.parent] = m
    resolved = {}
    manifest_notes = []
    for folder, m in manifests.items():
        listed = set()
        for entry in m["files"]:
            require(isinstance(entry, dict) and isinstance(entry.get("file"), str) and isinstance(entry.get("id"), str), "Malformed manifest inventory")
            require(Path(entry["file"]).name == entry["file"] and "/" not in entry["file"] and "\\" not in entry["file"] and ":" not in entry["file"], "Manifest filenames must stay in their directory")
            require(entry["file"] not in listed, "Duplicate filename in manifest")
            listed.add(entry["file"])
            supplied = safe_path(folder / entry["file"])
            renamed = safe_path(supplied.with_suffix(".txt"))
            if source.is_dir():
                require(supplied.is_file() or renamed.is_file(), "Manifest lists an export missing from the supplied directory")
        if source.is_file() and len(listed) > 1:
            manifest_notes.append("A single-file import covers only part of its neighboring manifest inventory.")
        if m.get("unavailable"):
            manifest_notes.append("A supplied manifest reports unavailable exports; completeness is not established.")
    for path, raw, data in pending:
        sha = hashlib.sha256(raw).hexdigest()
        own = challenge_name(data.get("challenge"))
        m = manifests.get(path.parent)
        if m:
            matches = [item for item in m["files"] if item["file"] == path.name or (path.suffix.lower() == ".txt" and Path(item["file"]).with_suffix(".txt").name == path.name)]
            require(len(matches) == 1 and matches[0]["id"] == data["submissionId"], "Submission does not match neighboring manifest")
            inherited = challenge_name(m["challenge"])
            require(not own or own == inherited, "Conflicting challenge metadata")
            own = inherited
        if own:
            require(sha not in resolved or resolved[sha] == own, "Conflicting challenge context for identical export")
            resolved[sha] = own
    return pending, resolved, ignored, manifest_notes


def extract(data, raw, challenge):
    sid = text(data.get("submissionId"), "Submission ID")
    for key in ("chatId", "scenario", "model", "status"):
        text(data.get(key), "Export " + key)
    submitted = timestamp(data.get("submittedAt"))
    messages = data.get("messages")
    require(isinstance(messages, list), "Export messages must be a list")
    previous = None
    tool_count = 0
    for message in messages:
        require(isinstance(message, dict) and isinstance(message.get("role"), str) and isinstance(message.get("content"), (str, type(None))), "Malformed message record")
        time = timestamp(message.get("timestamp"))
        require((previous is None or time >= previous) and time <= submitted, "Message timestamps are out of order or after submission")
        previous = time
        calls = message.get("toolCalls", [])
        if calls is None:
            calls = []
        require(isinstance(calls, list) and all(isinstance(c, dict) and isinstance(c.get("name"), str) and bool(c["name"].strip()) and "arguments" in c for c in calls), "Malformed or unsupported tool-call list")
        tool_count += len(calls)
    judge = data.get("judge")
    require(isinstance(judge, dict) and type(judge.get("isBreak")) is bool, "Export must include an explicit judge verdict")
    criterion_values = judge.get("criteria", [])
    criteria(criterion_values)
    if data["status"] in {"accepted", "rejected"}:
        require((data["status"] == "accepted") == judge["isBreak"], "Platform status and judge verdict disagree")
    record = {"id": "rec-" + hashlib.sha256(sid.encode("utf-8")).hexdigest()[:24], "challenge": challenge,
              "scenario": data["scenario"], "model": data["model"], "submitted_at": data["submittedAt"], "platform_status": data["status"],
              "chat_id": data["chatId"], "message_count": len(messages), "tool_call_count": tool_count,
              "evidence_level": "Exported platform judgment and message metadata; execution and hidden state are unverified.",
              "source_sha256": hashlib.sha256(raw).hexdigest(), "criteria": criterion_values}
    return record, {"message_hashes": [digest(m) for m in messages]}


def ingest(path, source):
    path = workspace_path(path)
    pending, contexts, ignored, notes = candidates(source)
    with locked(path):
        workspace, sources, snapshots = load(path)
        indexed = {v["submission_id"]: key for key, v in sources["records"].items()}
        existing = {r["id"]: r for r in workspace["records"]}
        for record in workspace["records"]:
            contexts.setdefault(record["source_sha256"], record["challenge"])
        added, duplicates = 0, 0
        for source_path, raw, data in pending:
            sha = hashlib.sha256(raw).hexdigest()
            require(sha in contexts, "Challenge context is missing; keep the export beside its manifest or provide an explicit challenge field")
            record, snapshot = extract(data, raw, contexts[sha])
            sid, rid = data["submissionId"], record["id"]
            if sid in indexed:
                old = sources["records"][indexed[sid]]
                require(old["sha256"] == sha and existing[indexed[sid]] == record, "Immutable submission conflict: same ID has different bytes or metadata")
                old["paths"] = sorted(set(old["paths"]) | {str(source_path)})
                duplicates += 1
                continue
            require(rid not in existing, "Stable record ID collision")
            workspace["records"].append(record)
            sources["records"][rid] = {"submission_id": sid, "sha256": sha, "paths": [str(source_path)]}
            snapshots["records"][rid] = snapshot
            indexed[sid] = rid
            existing[rid] = record
            added += 1
        workspace["records"].sort(key=lambda r: (timestamp(r["submitted_at"]), r["id"]))
        if notes:
            sources["import_notes"] = sorted(set(sources.get("import_notes", [])) | set(notes))
        recompute(workspace, snapshots)
        validate_workspace(workspace, taxonomy_ids())
        changed = commit(path, workspace, sources, snapshots)
        return {"added": added, "duplicate_files": duplicates, "ignored_non_export_files": ignored, "changed": changed,
                "summary": workspace["summary"], "warnings": snapshots["warnings"] + notes}


def add(path, file, replace=False):
    path = workspace_path(path)
    card = read_json(safe_path(file))
    with locked(path):
        workspace, sources, snapshots = load(path)
        validate_card(card, {r["id"] for r in workspace["records"]}, taxonomy_ids())
        old = next((c for c in workspace["cards"] if c["id"] == card["id"]), None)
        require(old is None or old == card or replace, "A different card already uses this ID; use --replace to preserve its history and revise it")
        if old is None:
            workspace["cards"].append(card)
        elif old != card:
            sources.setdefault("card_history", {}).setdefault(card["id"], []).append({"sha256": digest(old), "card": old})
            workspace["cards"][workspace["cards"].index(old)] = card
        changed = commit(path, workspace, sources, snapshots)
    return {"card_id": card["id"], "changed": changed}


def check(path):
    path = workspace_path(path)
    with locked(path):
        workspace, sources, snapshots = load(path)
    return {"valid": True, "summary": workspace["summary"], "card_count": len(workspace["cards"]), "warnings": snapshots["warnings"] + sources.get("import_notes", [])}


def brief(path):
    path = workspace_path(path)
    with locked(path):
        workspace, sources, snapshots = load(path)
    selected_cards = workspace["cards"][:8]
    references = {ref for card in selected_cards for ref in card["evidence_refs"]}
    ordered = sorted(workspace["records"], key=lambda r: (r["id"] not in references, r["submitted_at"], r["id"]))
    selected_records = ordered[:20]
    return {"title": workspace["title"], "selection_note": workspace["selection_note"], "limitations": workspace["limitations"],
            "summary": workspace["summary"], "cards": selected_cards, "records": selected_records, "record_ids": [r["id"] for r in selected_records],
            "omitted_card_count": len(workspace["cards"]) - len(selected_cards), "omitted_record_count": len(workspace["records"]) - len(selected_records),
            "warnings": snapshots["warnings"] + sources.get("import_notes", []), "assistant_handoff": "Maintain cards through the CLI. Cite record IDs, separate observations from hypotheses, preserve alternatives, and assess prior art before novelty. Do not infer authorship or causality from exported platform judgments. Source paths and transcript bodies are omitted from this brief."}
