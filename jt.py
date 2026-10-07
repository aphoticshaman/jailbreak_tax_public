"""Assistant-maintained offline research workspace commands."""
import argparse
import json
import sys
from scripts import workspace


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "ingest", "add", "check", "brief", "build"):
        command = commands.add_parser(name)
        command.add_argument("--workspace", required=True)
        if name == "init":
            command.add_argument("--name", required=True)
        elif name == "ingest":
            command.add_argument("source")
        elif name == "add":
            command.add_argument("--file", required=True)
            command.add_argument("--replace", action="store_true", help="Explicitly revise an existing card and preserve its prior version privately")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            result = workspace.init(args.workspace, args.name)
        elif args.command == "ingest":
            result = workspace.ingest(args.workspace, args.source)
        elif args.command == "add":
            result = workspace.add(args.workspace, args.file, replace=args.replace)
        elif args.command == "build":
            from scripts.build import build_private
            result = build_private(args.workspace)
        else:
            result = getattr(workspace, args.command)(args.workspace)
        print(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False))
        return 0
    except (workspace.WorkspaceError, OSError, KeyError, TypeError) as error:
        print("Error: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
