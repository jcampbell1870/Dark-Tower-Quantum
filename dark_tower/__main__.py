import argparse
import json
from pathlib import Path
import sys

from .runtime import MAX_SOURCE_BYTES, TowerError, parse, simulate


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="dark-tower", description="Dark Tower hosted quantum environment"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run a DTL quantum program")
    run.add_argument("source", type=Path)
    run.add_argument("--provider", choices=("local", "ibm"), default="local")
    run.add_argument("--shots", type=int, default=1024)
    run.add_argument("--seed", type=int, help="Local simulator only")
    run.add_argument("--backend", help="IBM backend name; otherwise least busy")
    run.add_argument(
        "--confirm-ibm", action="store_true", help="Consent to remote execution and charges"
    )
    portal = commands.add_parser("portal", help="Start the local browser portal")
    portal.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        if args.command == "portal":
            from .portal import serve
            serve(args.port)
            return 0
        if args.provider == "local" and (args.backend or args.confirm_ibm):
            raise TowerError("--backend and --confirm-ibm require --provider ibm.")
        if args.provider == "ibm" and (not args.confirm_ibm or args.seed is not None):
            raise TowerError("IBM requires --confirm-ibm and does not support --seed.")
        with args.source.open("rb") as source:
            data = source.read(MAX_SOURCE_BYTES + 1)
        if len(data) > MAX_SOURCE_BYTES:
            raise TowerError("Source exceeds 65536 bytes.")
        program = parse(data.decode("utf-8"))
        if args.provider == "ibm":
            from .ibm import run as run_ibm
            result = run_ibm(program, args.shots, args.backend)
        else:
            result = simulate(program, args.shots, args.seed)
        print(json.dumps(result, indent=2))
        return 0
    except (TowerError, OSError, UnicodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Stopped; any submitted IBM job must be managed on IBM Quantum Platform.",
              file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
