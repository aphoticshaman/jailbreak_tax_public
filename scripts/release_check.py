"""Check the explicit public file inventory and generated-page inputs.

This is a release guard, not a general secret detector or a safety classifier.
Editorial review is still required for public content.
"""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "PUBLIC_FILES.json"
PRIVATE_PARTS = {"private", "workspace", "workspaces", "sessions", "logs", "exports", "research"}
SENSITIVE_PATTERNS = [
    ("GitHub token pattern", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("GitHub fine-grained token pattern", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("private key header", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("credential assignment", re.compile(r'''(?i)(?:api[_-]?key|access[_-]?token|secret[_-]?key)\s*[:=]\s*["'][A-Za-z0-9_/-]{24,}["']''')),
    ("personal absolute path", re.compile(r"(?i)\b[A-Z]:[\\/]Users[\\/][A-Za-z0-9_. -]+[\\/]")),
]


class PageData(HTMLParser):
    def __init__(self):
        super().__init__()
        self.blocks: dict[str, str] = {}
        self.active: str | None = None
        self.errors: list[str] = []
        self.csp = ""

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "script":
            if values.get("src"):
                self.errors.append("Script source is external to the standalone artifact")
            if values.get("id") in {"catalog-data", "workspace-data"}:
                self.active = values["id"]
                if self.active in self.blocks:
                    self.errors.append("Duplicate embedded data block")
                self.blocks[self.active] = ""
        if tag == "meta" and values.get("http-equiv", "").lower() == "content-security-policy":
            self.csp = values.get("content", "")
        if any(key.lower().startswith("on") for key in values):
            self.errors.append("Inline event handler found")
        if tag in {"iframe", "object", "embed", "base"}:
            self.errors.append("Unexpected active embedded content")
        if tag in {"img", "audio", "video", "source", "link"}:
            location = values.get("src", values.get("href", ""))
            if location and not location.startswith(("data:", "#")):
                self.errors.append("Non-embedded resource in standalone artifact")

    def handle_data(self, data):
        if self.active:
            self.blocks[self.active] += data

    def handle_endtag(self, tag):
        if tag == "script":
            self.active = None


def checked_files(root: Path, names: list[str]) -> list[Path]:
    if not isinstance(names, list) or not names or any(not isinstance(v, str) for v in names):
        raise ValueError("Public inventory must be a nonempty array of file paths")
    if len(names) != len(set(names)):
        raise ValueError("Duplicate public inventory entry")
    files = []
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
            raise ValueError("Unsafe public inventory path")
        if any(part.lower() in PRIVATE_PARTS for part in path.parts):
            raise ValueError("Private directory in public inventory")
        if (name.lower().endswith(".private.json")
                or path.name.casefold() in {"research.html", "workspace.json"}
                or path.name.casefold().startswith("submission-")):
            raise ValueError("Private artifact in public inventory")
        target = root.joinpath(*path.parts)
        for current in [target, *target.parents]:
            if current == root.parent:
                break
            if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
                raise ValueError("Linked path in public inventory")
        if not target.is_file() or not target.resolve().is_relative_to(root.resolve()):
            raise ValueError("Missing or escaping public inventory path: " + name)
        if target.stat().st_size > 8_000_000:
            raise ValueError("Unexpectedly large public asset: " + name)
        files.append(target)
    return files


def check(root: Path, check_git: bool = True) -> list[str]:
    inventory = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    files = checked_files(root, inventory)
    errors = []
    if MANIFEST not in inventory:
        errors.append("The public inventory must include itself")
    for path in files:
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append("Unexpected binary asset: " + path.relative_to(root).as_posix())
            continue
        for label, pattern in SENSITIVE_PATTERNS:
            if pattern.search(content):
                errors.append(path.relative_to(root).as_posix() + ": " + label)

    catalog = json.loads((root / "data/catalog.json").read_text(encoding="utf-8"))
    demo = json.loads((root / "examples/demo-workspace.json").read_text(encoding="utf-8"))
    if demo.get("visibility") != "demo":
        errors.append("Public example must be marked demo")
    for record in demo.get("records", []):
        if not record.get("id", "").startswith("demo-") or not record.get("chat_id", "").startswith("demo-"):
            errors.append("Public example identifiers must explicitly be demo identifiers")
    for name in ("START.html", "index.html"):
        page = PageData()
        page.feed((root / name).read_text(encoding="utf-8"))
        errors.extend(name + ": " + error for error in page.errors)
        if "connect-src 'none'" not in page.csp or "default-src 'none'" not in page.csp:
            errors.append(name + ": restrictive offline CSP missing")
        for key, expected in (("catalog-data", catalog), ("workspace-data", demo)):
            try:
                actual = json.loads(page.blocks.get(key, ""))
            except ValueError:
                errors.append(name + ": missing or invalid " + key)
                continue
            if actual != expected:
                errors.append(name + ": embedded data differs from allowlisted public input: " + key)
    if (root / "START.html").read_bytes() != (root / "index.html").read_bytes():
        errors.append("Offline and hosted generated pages differ")

    if check_git and (root / ".git").exists():
        result = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True)
        tracked = set(result.stdout.decode("utf-8").split("\0")) - {""}
        if tracked and tracked != set(inventory):
            errors.append("Tracked file list differs from reviewed public inventory")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        errors = check(args.root.resolve())
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print("Release check failed: " + str(error), file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print("FAIL: " + error, file=sys.stderr)
        return 1
    print("Public inventory, generated inputs, offline policy, and credential-pattern checks passed.")
    print("Editorial content review and fresh-history review remain separate checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
