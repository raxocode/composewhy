"""Secret redaction and value non-leakage tests.

Ensures that environment variable values and fake secret sentinels
NEVER leak into stdout, stderr, JSON output, or exception strings under any
circumstances, including normal runs, fallback paths, and error scenarios.
"""

import json
from pathlib import Path
import pytest

from composewhy.cli import main
from composewhy.explain import explain_variable
from composewhy.output import render_human_text, render_json
import io
from conftest import mock_docker_with_env

FAKE_SENTINEL_LITERAL = "CW_FAKE_SECRET_LITERAL_93a2_SUPERSECRET"
FAKE_SENTINEL_ENV_FILE = "CW_FAKE_SECRET_ENVFILE_b81c_VERYSECRET"
FAKE_SENTINEL_SHELL = "CW_FAKE_SECRET_SHELL_44d1_TOPSECRET"
FAKE_SENTINEL_RAW_STDERR = "CW_FAKE_SECRET_STDERR_99ee_PASSWORDFOUND"


def _assert_no_sentinels(text: str):
    assert FAKE_SENTINEL_LITERAL not in text, f"Sentinel leaked in output: {text}"
    assert FAKE_SENTINEL_ENV_FILE not in text, f"Sentinel leaked in output: {text}"
    assert FAKE_SENTINEL_SHELL not in text, f"Sentinel leaked in output: {text}"
    assert FAKE_SENTINEL_RAW_STDERR not in text, f"Sentinel leaked in output: {text}"


def test_redaction_literal_mapping(tmp_path: Path, capsys):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        f"services:\n"
        f"  web:\n"
        f"    environment:\n"
        f"      API_KEY: '{FAKE_SENTINEL_LITERAL}'\n"
    )
    mock_docker_with_env("web", {"API_KEY": FAKE_SENTINEL_LITERAL})

    # CLI human mode
    ret = main(["explain", "--file", str(compose), "web", "API_KEY"])
    assert ret == 0
    captured = capsys.readouterr()
    _assert_no_sentinels(captured.out)
    _assert_no_sentinels(captured.err)

    # CLI JSON mode
    ret_json = main(["explain", "--file", str(compose), "--json", "web", "API_KEY"])
    assert ret_json == 0
    captured_json = capsys.readouterr()
    _assert_no_sentinels(captured_json.out)
    _assert_no_sentinels(captured_json.err)

    # Model fields check
    res = explain_variable(compose, "web", "API_KEY")
    _assert_no_sentinels(res.explanation)
    if res.winner:
        _assert_no_sentinels(str(res.winner.path))
        _assert_no_sentinels(res.winner.kind)
    for c in res.candidates:
        if c.note:
            _assert_no_sentinels(c.note)
        _assert_no_sentinels(str(c.source.path))


def test_redaction_env_file_and_shell(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.setenv("SECRET_TOKEN", FAKE_SENTINEL_SHELL)

    env_file = tmp_path / ".env"
    env_file.write_text(f"SECRET_TOKEN={FAKE_SENTINEL_ENV_FILE}\n")

    compose = tmp_path / "compose.yaml"
    compose.write_text(
        f"services:\n"
        f"  web:\n"
        f"    env_file: .env\n"
        f"    environment:\n"
        f"      SECRET_TOKEN: ${{SECRET_TOKEN}}\n"
    )
    mock_docker_with_env("web", {"SECRET_TOKEN": FAKE_SENTINEL_SHELL})

    # CLI human mode
    ret = main(["explain", "--file", str(compose), "web", "SECRET_TOKEN"])
    assert ret == 0
    captured = capsys.readouterr()
    _assert_no_sentinels(captured.out)
    _assert_no_sentinels(captured.err)

    # CLI JSON mode
    ret_json = main(["explain", "--file", str(compose), "--json", "web", "SECRET_TOKEN"])
    assert ret_json == 0
    captured_json = capsys.readouterr()
    _assert_no_sentinels(captured_json.out)
    _assert_no_sentinels(captured_json.err)


def test_redaction_on_error_paths(tmp_path: Path, capsys, monkeypatch):
    # Malformed YAML containing secret
    bad_compose = tmp_path / "compose.yaml"
    bad_compose.write_text(f"services: [invalid_yaml: {FAKE_SENTINEL_LITERAL}\n")

    ret = main(["explain", "--file", str(bad_compose), "web", "VAR"])
    assert ret == 4
    captured = capsys.readouterr()
    _assert_no_sentinels(captured.out)
    _assert_no_sentinels(captured.err)

    # JSON error mode
    ret_json = main(["explain", "--file", str(bad_compose), "--json", "web", "VAR"])
    assert ret_json == 4
    captured_json = capsys.readouterr()
    _assert_no_sentinels(captured_json.out)
    _assert_no_sentinels(captured_json.err)


def test_redaction_docker_failure_masks_stderr(tmp_path: Path, capsys):
    from composewhy.docker_compose import set_custom_compose_runner
    from composewhy.errors import DockerError

    def failing_runner(cmd, cwd, timeout):
        # Stderr simulates Docker leaking a token in command failure output
        return 1, b"", f"error: unauthorized to connect with token={FAKE_SENTINEL_RAW_STDERR}".encode("utf-8")

    set_custom_compose_runner(failing_runner)

    compose = tmp_path / "compose.yaml"
    compose.write_text("services:\n  web:\n    image: busybox\n")

    ret = main(["explain", "--file", str(compose), "web", "VAR"])
    assert ret == 5
    captured = capsys.readouterr()
    _assert_no_sentinels(captured.out)
    _assert_no_sentinels(captured.err)

    # Verify sanitized message is shown instead
    assert "docker compose config failed" in captured.err.lower()
