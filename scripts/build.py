"""Deterministic standalone renderer. Public builds read only fixed public inputs."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

if __package__:
    from . import workspace as ws
    from .check_catalog import validate_catalog as catalog_errors
else:
    import workspace as ws
    from check_catalog import validate_catalog as catalog_errors

ROOT = Path(__file__).resolve().parents[1]


def validate_catalog(catalog):
    errors = catalog_errors(catalog)
    ws.require(not errors, "Invalid public catalog: " + "; ".join(errors))
    return {entry["id"] for entry in catalog["entries"]}


def escaped_json(value):
    result = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    for character, replacement in (("&", "\\u0026"), ("<", "\\u003c"), (">", "\\u003e"), ("\u2028", "\\u2028"), ("\u2029", "\\u2029")):
        result = result.replace(character, replacement)
    return result


def render(root, catalog, workspace):
    root = ws.safe_path(root)
    ids = validate_catalog(catalog)
    ws.validate_workspace(workspace, ids)
    template = ws.safe_path(root / "web" / "index.html").read_text(encoding="utf-8")
    css = ws.safe_path(root / "web" / "style.css").read_text(encoding="utf-8")
    javascript = ws.safe_path(root / "web" / "app.js").read_text(encoding="utf-8")
    replacements = {"/* APP_STYLES */": css, "/* APP_SCRIPT */": javascript,
                    "CATALOG_JSON": escaped_json(catalog), "WORKSPACE_JSON": escaped_json(workspace)}
    for marker in replacements:
        ws.require(template.count(marker) == 1, "Template must contain exactly one " + marker)
    # One substitution pass: data containing another marker stays inert data.
    pattern = re.compile("|".join(re.escape(marker) for marker in replacements))
    return pattern.sub(lambda m: replacements[m.group(0)], template).encode("utf-8")


def build_public(root=None):
    root = ws.safe_path(root or ROOT)
    catalog = ws.read_json(ws.safe_path(root / "data" / "catalog.json"))
    demo = ws.read_json(ws.safe_path(root / "examples" / "demo-workspace.json"))
    ws.require(demo.get("visibility") == "demo", "Public builds require the explicitly fictional demo workspace")
    ws.require(all(r.get("id", "").startswith("demo-") and r.get("chat_id", "").startswith("demo-") for r in demo.get("records", [])), "Public demo identifiers must use the demo- prefix")
    output = render(root, catalog, demo)
    destinations = [ws.safe_path(root / name) for name in ("START.html", "index.html")]
    old = {p: p.read_bytes() if p.exists() else None for p in destinations}
    changed = []
    try:
        for path in destinations:
            if old[path] != output:
                ws.atomic_write(path, output)
                changed.append(path)
    except BaseException:
        for path in changed:
            if old[path] is None:
                path.unlink(missing_ok=True)
            else:
                ws.atomic_write(path, old[path])
        raise
    return {"artifacts": [str(p) for p in destinations], "bytes_each": len(output)}


def build_private(path):
    path = ws.workspace_path(path)
    with ws.locked(path):
        workspace, _, _ = ws.load(path)
        catalog = ws.read_json(ws.safe_path(ROOT / "data" / "catalog.json"))
        output = render(ROOT, catalog, workspace)
        destination = ws.safe_path(path / "RESEARCH.html")
        if not destination.exists() or destination.read_bytes() != output:
            ws.atomic_write(destination, output)
    return {"artifact": str(destination), "bytes": len(output)}


def main():
    try:
        print(json.dumps(build_public(), indent=2))
        return 0
    except (ws.WorkspaceError, OSError, KeyError, TypeError) as error:
        print("Build failed: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
