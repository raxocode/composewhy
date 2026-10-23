"""Command-line interface entry point for ComposeWhy."""

import argparse
import sys
from pathlib import Path
from typing import Optional, List

from . import __version__
from .explain import explain_variable
from .output import render_human_text, render_json
from .models import ExplainResult
from .errors import (
    ComposeWhyExitCode,
    ComposeWhyError,
    UsageError,
    InputError,
    DockerError,
    UnsupportedError,
)


class ComposeWhyArgumentParser(argparse.ArgumentParser):
    def error(self, message: str):
        sys.stderr.write(f"Error: {message}\n")
        sys.exit(ComposeWhyExitCode.USAGE_ERROR)


def build_parser() -> argparse.ArgumentParser:
    parser = ComposeWhyArgumentParser(
        prog="composewhy",
        description="Explain Docker Compose environment-variable provenance without revealing values.",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    # version
    subparsers.add_parser("version", help="Print product version and exit")

    # explain
    explain_parser = subparsers.add_parser("explain", help="Explain variable provenance for a service")
    explain_parser.add_argument(
        "--file",
        "-f",
        dest="file",
        required=True,
        type=Path,
        help="Path to compose.yaml file",
    )
    explain_parser.add_argument(
        "--env-file",
        dest="env_file",
        type=Path,
        default=None,
        help="Optional path to project environment file",
    )
    explain_parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON without values",
    )
    explain_parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Subprocess timeout in seconds (1..30, default: 10)",
    )
    explain_parser.add_argument("service", help="Target service name in Compose file")
    explain_parser.add_argument("variable", help="Target environment variable name")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()

    if argv is None:
        argv = sys.argv[1:]

    # Handle bare 'composewhy' or '--help' / '-h'
    if not argv:
        parser.print_help()
        return ComposeWhyExitCode.EXPLAINED

    if argv[0] in ("--help", "-h"):
        parser.print_help()
        return ComposeWhyExitCode.EXPLAINED

    if argv[0] in ("--version", "-v"):
        sys.stdout.write(f"composewhy {__version__}\n")
        return ComposeWhyExitCode.EXPLAINED

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return e.code

    if args.subcommand == "version":
        sys.stdout.write(f"composewhy {__version__}\n")
        return ComposeWhyExitCode.EXPLAINED

    if args.subcommand == "explain":
        # Validate timeout
        if args.timeout < 1 or args.timeout > 30:
            sys.stderr.write("Error: --timeout must be an integer between 1 and 30\n")
            return ComposeWhyExitCode.USAGE_ERROR

        is_json = bool(args.json)

        try:
            result = explain_variable(
                compose_path=args.file,
                service_name=args.service,
                variable_name=args.variable,
                env_file_path=args.env_file,
                timeout=args.timeout,
            )

            if is_json:
                render_json(result, sys.stdout)
            else:
                render_human_text(result, sys.stdout)

            return result.exit_code

        except ComposeWhyError as err:
            if is_json:
                err_result = ExplainResult(
                    service=args.service,
                    variable=args.variable,
                    status="error",
                    effective_presence="unknown",
                    reason_code=err.__class__.__name__.upper(),
                    explanation=err.message,
                    exit_code=err.exit_code,
                )
                render_json(err_result, sys.stdout)
            else:
                sys.stderr.write(f"Error [{err.__class__.__name__}]: {err.message}\n")
            return err.exit_code

        except Exception:
            # Mask internal traceback
            sys.stderr.write("Internal error: unexpected failure occurred during explanation\n")
            return ComposeWhyExitCode.INTERNAL_ERROR

    parser.print_help()
    return ComposeWhyExitCode.USAGE_ERROR


if __name__ == "__main__":
    sys.exit(main())
