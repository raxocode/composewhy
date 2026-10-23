"""CLI interface, flag parsing, and exit code tests."""

import json
from pathlib import Path
from composewhy.cli import main
from composewhy.errors import ComposeWhyExitCode


def test_cli_help(capsys):
    ret = main(["--help"])
    assert ret == ComposeWhyExitCode.EXPLAINED
    captured = capsys.readouterr()
    assert "Explain Docker Compose environment-variable provenance" in captured.out


def test_cli_version(capsys):
    ret = main(["version"])
    assert ret == ComposeWhyExitCode.EXPLAINED
    captured = capsys.readouterr()
    assert "composewhy 0.1.0" in captured.out


def test_cli_unknown_flag(capsys, tmp_path: Path):
    compose_file = tmp_path / "compose.yaml"
    compose_file.write_text("services:\n  web:\n    image: busybox\n")
    ret = main(["explain", "--file", str(compose_file), "web", "VAR", "--invalid-flag"])
    assert ret == ComposeWhyExitCode.USAGE_ERROR
    captured = capsys.readouterr()
    assert "unrecognized arguments" in captured.err.lower()


def test_cli_missing_required_args(capsys):
    ret = main(["explain"])
    assert ret == ComposeWhyExitCode.USAGE_ERROR
    captured = capsys.readouterr()
    assert "Error:" in captured.err


def test_cli_invalid_timeout(tmp_path: Path, capsys):
    compose_file = tmp_path / "compose.yaml"
    compose_file.write_text("services:\n  web:\n    image: busybox\n")
    ret = main(["explain", "--file", str(compose_file), "--timeout", "0", "web", "VAR"])
    assert ret == ComposeWhyExitCode.USAGE_ERROR
    captured = capsys.readouterr()
    assert "--timeout must be an integer between 1 and 30" in captured.err

    ret31 = main(["explain", "--file", str(compose_file), "--timeout", "31", "web", "VAR"])
    assert ret31 == ComposeWhyExitCode.USAGE_ERROR


def test_cli_invalid_variable_name(tmp_path: Path, capsys):
    compose_file = tmp_path / "compose.yaml"
    compose_file.write_text("services:\n  web:\n    image: busybox\n")
    ret = main(["explain", "--file", str(compose_file), "web", "invalid-var-name!"])
    assert ret == ComposeWhyExitCode.INPUT_ERROR
    captured = capsys.readouterr()
    assert "Invalid variable name" in captured.err
