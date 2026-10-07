"""Validate the public catalog's explicit schema and internal references.

This performs no network requests and reads only the requested catalog.
Structural checks do not replace editorial or primary-source review.
"""
from __future__ import annotations

import argparse
from datetime import date
import ipaddress
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
ID = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)?$")
TOP = {"schema_version", "title", "updated", "summary", "categories", "entries", "sources", "evaluation_dimensions", "learning_paths"}
SHAPES = {
    "categories": {"id", "name", "summary"},
    "entries": {"id", "category_id", "name", "summary", "boundary", "evidence_to_check", "alternative_explanations", "defensive_questions", "source_ids", "epistemic_status", "related_ids"},
    "sources": {"id", "title", "url", "year", "reviewed_on", "review_depth", "scope_note"},
    "evaluation_dimensions": {"id", "name", "question", "why_it_matters"},
    "learning_paths": {"id", "title", "summary", "entry_ids", "questions"},
}
LIST_FIELDS = {"evidence_to_check", "alternative_explanations", "defensive_questions", "source_ids", "related_ids", "entry_ids", "questions"}


def valid_https(value: str) -> bool:
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value) or "\\" in value:
        return False
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if parsed.scheme != "https" or not host or parsed.username is not None or parsed.password is not None:
            return False
        if parsed.port not in (None, 443) or host.lower() in {"localhost", "localhost."} or host.lower().endswith((".localhost", ".local")):
            return False
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return "." in host and not host.startswith(".") and not host.endswith(".")
        return False
    except ValueError:
        return False


def validate_catalog(data: object) -> list[str]:
    errors: list[str] = []

    def problem(where: str, message: str) -> None:
        errors.append(f"{where}: {message}")

    def text(value: object, where: str) -> bool:
        if not isinstance(value, str) or not value.strip():
            problem(where, "expected nonempty text")
            return False
        if "\x00" in value:
            problem(where, "text contains a null character")
        return True

    def day(value: object, where: str) -> date | None:
        if not isinstance(value, str):
            problem(where, "expected an ISO calendar date")
            return None
        try:
            result = date.fromisoformat(value)
            if result.isoformat() != value:
                raise ValueError
            return result
        except ValueError:
            problem(where, "expected an ISO calendar date")
            return None

    if not isinstance(data, dict):
        return ["catalog: expected an object"]
    if set(data) != TOP:
        problem("catalog", "missing or unknown top-level fields")
    if type(data.get("schema_version")) is not int or data.get("schema_version") != 1:
        problem("schema_version", "expected integer 1")
    for key in ("title", "summary"):
        text(data.get(key), key)
    updated = day(data.get("updated"), "updated")

    indexes: dict[str, dict[str, dict]] = {}
    for group, expected in SHAPES.items():
        rows = data.get(group)
        indexes[group] = {}
        if not isinstance(rows, list) or not rows:
            problem(group, "expected a nonempty array")
            continue
        for number, row in enumerate(rows):
            where = f"{group}[{number}]"
            if not isinstance(row, dict):
                problem(where, "expected an object")
                continue
            if set(row) != expected:
                problem(where, "missing or unknown fields")
            for key in expected:
                value = row.get(key)
                location = f"{where}.{key}"
                if key in LIST_FIELDS:
                    if not isinstance(value, list) or not value:
                        problem(location, "expected a nonempty text array")
                        continue
                    for i, item in enumerate(value):
                        text(item, f"{location}[{i}]")
                    if all(isinstance(item, str) for item in value) and len(set(value)) != len(value):
                        problem(location, "duplicate values")
                elif key == "year":
                    if type(value) is not int or not 1800 <= value <= 2100:
                        problem(location, "expected an integer publication year")
                else:
                    text(value, location)
            identifier = row.get("id")
            if not isinstance(identifier, str) or not ID.fullmatch(identifier):
                problem(f"{where}.id", "invalid identifier")
                continue
            if identifier in indexes[group]:
                problem(f"{where}.id", "duplicate identifier")
            indexes[group][identifier] = row

    for identifier, entry in indexes["entries"].items():
        category = entry.get("category_id")
        if not isinstance(category, str) or category not in indexes["categories"]:
            problem(identifier, "unknown category reference")
        elif not identifier.startswith(category + "."):
            problem(identifier, "entry identifier does not match its category")
        for field, target in (("source_ids", "sources"), ("related_ids", "entries")):
            values = entry.get(field)
            if isinstance(values, list):
                for value in values:
                    if not isinstance(value, str) or value not in indexes[target]:
                        problem(f"{identifier}.{field}", "unresolved reference")
                    elif field == "related_ids" and value == identifier:
                        problem(f"{identifier}.{field}", "self-reference is not a related entry")

    used_categories = {row.get("category_id") for row in indexes["entries"].values() if isinstance(row.get("category_id"), str)}
    for identifier in indexes["categories"]:
        if identifier not in used_categories:
            problem(identifier, "category has no entries")
    for identifier, path in indexes["learning_paths"].items():
        values = path.get("entry_ids")
        if isinstance(values, list):
            for value in values:
                if not isinstance(value, str) or value not in indexes["entries"]:
                    problem(f"{identifier}.entry_ids", "unresolved reference")
    for identifier, source in indexes["sources"].items():
        if not valid_https(source.get("url")):
            problem(f"{identifier}.url", "expected a public HTTPS URL without credentials")
        reviewed = day(source.get("reviewed_on"), f"{identifier}.reviewed_on")
        if reviewed and updated and reviewed > updated:
            problem(identifier, "source review is newer than the catalog update")
        if reviewed and type(source.get("year")) is int and source["year"] > reviewed.year:
            problem(identifier, "publication year is later than the recorded review")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", nargs="?", type=Path, default=ROOT / "data/catalog.json")
    args = parser.parse_args()
    try:
        data = json.loads(args.catalog.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"Catalog could not be read: {type(error).__name__}")
        return 1
    errors = validate_catalog(data)
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"Catalog valid: {len(data['entries'])} entries, {len(data['categories'])} categories, {len(data['sources'])} sources, {len(data['evaluation_dimensions'])} evaluation dimensions, {len(data['learning_paths'])} reading paths.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
