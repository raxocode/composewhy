"""Unit tests covering U01 through U36 from 03-TESTS-AND-ACCEPTANCE.md."""

import os
import json
import pytest
from pathlib import Path

from composewhy.cli import main
from composewhy.explain import explain_variable
from composewhy.docker_compose import set_custom_compose_runner
from composewhy.errors import ComposeWhyExitCode, InputError, DockerError


def mock_docker_with_env(service_name: str, env_dict: dict):
    def runner(args, cwd, timeout):
        output = json.dumps({"services": {service_name: {"environment": env_dict}}}).encode("utf-8")
        return (0, output, b"")
    set_custom_compose_runner(runner)


def test_u01_literal_mapping(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    image: busybox\n"
        "    environment:\n"
        "      APP_MODE: production\n"
    )
    mock_docker_with_env("web", {"APP_MODE": "production"})

    res = explain_variable(compose, "web", "APP_MODE")
    assert res.status == "explained"
    assert res.exit_code == ComposeWhyExitCode.EXPLAINED
    assert res.winner is not None
    assert res.winner.kind == "service_environment"
    assert res.winner.line == 5


def test_u02_literal_list(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    image: busybox\n"
        "    environment:\n"
        "      - APP_MODE=production\n"
    )
    mock_docker_with_env("web", {"APP_MODE": "production"})

    res = explain_variable(compose, "web", "APP_MODE")
    assert res.status == "explained"
    assert res.winner is not None
    assert res.winner.line == 5


def test_u03_list_multiple_equals(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    environment:\n"
        "      - TOKEN=a=b=c\n"
    )
    mock_docker_with_env("web", {"TOKEN": "a=b=c"})

    res = explain_variable(compose, "web", "TOKEN")
    assert res.status == "explained"
    assert res.winner is not None
    assert res.winner.key == "TOKEN"


def test_u04_empty_literal_mapping(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    environment:\n"
        "      APP_MODE: \"\"\n"
    )
    mock_docker_with_env("web", {"APP_MODE": ""})

    res = explain_variable(compose, "web", "APP_MODE")
    assert res.status == "explained"
    assert res.effective_presence == "present"


def test_u05_empty_literal_list(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    environment:\n"
        "      - APP_MODE=\n"
    )
    mock_docker_with_env("web", {"APP_MODE": ""})

    res = explain_variable(compose, "web", "APP_MODE")
    assert res.status == "explained"
    assert res.effective_presence == "present"


def test_u06_interpolation_shell_wins(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DB_URL", "postgres://localhost/test")
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    environment:\n"
        "      DATABASE_URL: ${DB_URL}\n"
    )
    mock_docker_with_env("web", {"DATABASE_URL": "postgres://localhost/test"})

    res = explain_variable(compose, "web", "DATABASE_URL")
    assert res.status == "explained"
    assert res.winner is not None
    assert res.winner.kind == "service_environment"
    assert res.interpolation_source == "shell DB_URL"


def test_u07_interpolation_project_env_wins(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DB_URL", raising=False)
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    environment:\n"
        "      DATABASE_URL: ${DB_URL}\n"
    )
    env_file = tmp_path / ".env"
    env_file.write_text("DB_URL=sqlite:///db.sqlite\n")
    mock_docker_with_env("web", {"DATABASE_URL": "sqlite:///db.sqlite"})

    res = explain_variable(compose, "web", "DATABASE_URL")
    assert res.status == "explained"
    assert res.winner is not None
    assert ".env:1 (DB_URL)" in (res.interpolation_source or "")


def test_u08_interpolation_shell_overrides_env_file(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DB_URL", "shell-db-url")
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    environment:\n"
        "      DATABASE_URL: ${DB_URL}\n"
    )
    env_file = tmp_path / ".env"
    env_file.write_text("DB_URL=file-db-url\n")
    mock_docker_with_env("web", {"DATABASE_URL": "shell-db-url"})

    res = explain_variable(compose, "web", "DATABASE_URL")
    assert res.status == "explained"
    assert res.interpolation_source == "shell DB_URL"
    assert len(res.candidates) == 1
    assert res.candidates[0].outcome == "overridden"


def test_u09_project_env_alone_does_not_inject(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    image: busybox\n"
    )
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=db-url\n")
    mock_docker_with_env("web", {})

    res = explain_variable(compose, "web", "DATABASE_URL")
    assert res.status == "unknown"
    assert res.reason_code == "POSSIBLE_IMAGE_ENV"
    assert len(res.candidates) == 1
    assert res.candidates[0].outcome == "unused"


def test_u10_single_service_env_file(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    env_file:\n"
        "      - base.env\n"
    )
    base_env = tmp_path / "base.env"
    base_env.write_text("API_KEY=xyz\n")
    mock_docker_with_env("web", {"API_KEY": "xyz"})

    res = explain_variable(compose, "web", "API_KEY")
    assert res.status == "explained"
    assert res.winner is not None
    assert res.winner.kind == "service_env_file"
    assert res.winner.line == 1


def test_u11_multiple_env_files_last_wins(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    env_file:\n"
        "      - first.env\n"
        "      - second.env\n"
    )
    (tmp_path / "first.env").write_text("VAR=first\n")
    (tmp_path / "second.env").write_text("VAR=second\n")
    mock_docker_with_env("web", {"VAR": "second"})

    res = explain_variable(compose, "web", "VAR")
    assert res.status == "explained"
    assert res.winner is not None
    assert "second.env" in (res.winner.path or "")
    assert len(res.candidates) == 1
    assert res.candidates[0].outcome == "overridden"
    assert "first.env" in (res.candidates[0].source.path or "")


def test_u12_environment_overrides_env_file(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    env_file:\n"
        "      - extra.env\n"
        "    environment:\n"
        "      VAR: \"\"\n"
    )
    (tmp_path / "extra.env").write_text("VAR=extra_val\n")
    mock_docker_with_env("web", {"VAR": ""})

    res = explain_variable(compose, "web", "VAR")
    assert res.status == "explained"
    assert res.winner is not None
    assert res.winner.kind == "service_environment"
    assert len(res.candidates) == 1
    assert res.candidates[0].outcome == "overridden"


def test_u14_variable_belongs_to_different_service(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  backend:\n"
        "    environment:\n"
        "      SECRET_KEY: 123\n"
        "  web:\n"
        "    image: busybox\n"
    )
    mock_docker_with_env("web", {})

    res = explain_variable(compose, "web", "SECRET_KEY")
    assert res.status == "unknown"
    assert res.reason_code == "POSSIBLE_IMAGE_ENV"


def test_u15_unsupported_interpolation_syntax(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    environment:\n"
        "      VAR: ${FOO:-default_val}\n"
    )
    mock_docker_with_env("web", {"VAR": "default_val"})

    res = explain_variable(compose, "web", "VAR")
    assert res.status == "unknown"
    assert res.reason_code == "UNSUPPORTED_INTERPOLATION"


def test_u16_bare_list_entry(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    environment:\n"
        "      - BARE_PASS_THROUGH\n"
    )
    mock_docker_with_env("web", {"BARE_PASS_THROUGH": "val"})

    res = explain_variable(compose, "web", "BARE_PASS_THROUGH")
    assert res.status == "unknown"
    assert res.reason_code == "UNSUPPORTED_PASS_THROUGH"


def test_u17_null_environment_value(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    environment:\n"
        "      NULL_VAR: null\n"
    )
    mock_docker_with_env("web", {})

    res = explain_variable(compose, "web", "NULL_VAR")
    assert res.status == "unknown"
    assert res.reason_code == "UNSUPPORTED_NULL_ENV"


def test_u18_unsupported_compose_feature(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    extends: base\n"
        "    environment:\n"
        "      VAR: val\n"
    )
    mock_docker_with_env("web", {"VAR": "val"})

    res = explain_variable(compose, "web", "VAR")
    assert res.status == "unknown"
    assert res.reason_code == "UNSUPPORTED_COMPOSE_FEATURE"


def test_u19_duplicate_environment_key(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    environment:\n"
        "      DUP_KEY: first\n"
        "      DUP_KEY: second\n"
    )
    mock_docker_with_env("web", {"DUP_KEY": "second"})

    res = explain_variable(compose, "web", "DUP_KEY")
    assert res.status == "unknown"
    assert res.reason_code == "DUPLICATE_KEY"


def test_u20_missing_referenced_env_file(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    env_file:\n"
        "      - missing.env\n"
    )
    mock_docker_with_env("web", {})

    with pytest.raises(InputError) as exc_info:
        explain_variable(compose, "web", "VAR")
    assert "missing.env" in exc_info.value.message


def test_u22_env_file_duplicate_keys(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    env_file:\n"
        "      - test.env\n"
    )
    (tmp_path / "test.env").write_text("VAR=1\nVAR=2\n")
    mock_docker_with_env("web", {"VAR": "2"})

    res = explain_variable(compose, "web", "VAR")
    assert res.status == "unknown"
    assert res.reason_code == "DUPLICATE_KEY_IN_ENV_FILE"


def test_u23_service_missing(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  api:\n"
        "    image: busybox\n"
    )
    with pytest.raises(InputError) as exc:
        explain_variable(compose, "nonexistent", "VAR")
    assert "nonexistent" in exc.value.message


def test_u24_inconsistent_resolution_missing_in_docker(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    environment:\n"
        "      VAR: val\n"
    )
    # Docker config model omits VAR
    mock_docker_with_env("web", {})

    res = explain_variable(compose, "web", "VAR")
    assert res.status == "unknown"
    assert res.reason_code == "INCONSISTENT_RESOLUTION"


def test_u25_unattributed_effective_value(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    image: busybox\n"
    )
    # Docker config model has VAR, but raw YAML and env_file don't
    mock_docker_with_env("web", {"SURPRISE_VAR": "val"})

    res = explain_variable(compose, "web", "SURPRISE_VAR")
    assert res.status == "unknown"
    assert res.reason_code == "UNATTRIBUTED_EFFECTIVE_VALUE"


def test_u26_docker_process_unavailable(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text("services:\n  web:\n    image: busybox\n")

    def fail_runner(args, cwd, timeout):
        raise DockerError("Docker executable 'docker' is not available in system PATH")

    set_custom_compose_runner(fail_runner)
    with pytest.raises(DockerError):
        explain_variable(compose, "web", "VAR")


def test_u27_docker_nonzero_exit_masks_secrets(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text("services:\n  web:\n    image: busybox\n")

    secret_sentinel = "CW_FAKE_SECRET_IN_STDERR_93a2"
    def error_runner(args, cwd, timeout):
        return (1, b"", f"FATAL error occurred with secret: {secret_sentinel}".encode("utf-8"))

    set_custom_compose_runner(error_runner)
    with pytest.raises(DockerError) as exc:
        explain_variable(compose, "web", "VAR")
    assert secret_sentinel not in exc.value.message


def test_u28_docker_timeout(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text("services:\n  web:\n    image: busybox\n")

    def timeout_runner(args, cwd, timeout):
        raise DockerError(f"Docker Compose config command timed out after {timeout} seconds")

    set_custom_compose_runner(timeout_runner)
    with pytest.raises(DockerError) as exc:
        explain_variable(compose, "web", "VAR", timeout=5)
    assert "timed out after 5 seconds" in exc.value.message


def test_u29_docker_output_too_large(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text("services:\n  web:\n    image: busybox\n")

    def huge_runner(args, cwd, timeout):
        return (0, b"x" * (5 * 1024 * 1024 + 1), b"")

    set_custom_compose_runner(huge_runner)
    with pytest.raises(DockerError) as exc:
        explain_variable(compose, "web", "VAR")
    assert "exceeded 5 MiB" in exc.value.message


def test_u30_json_mode_explained(tmp_path: Path, capsys):
    compose = tmp_path / "compose.yaml"
    compose.write_text("services:\n  web:\n    environment:\n      FOO: bar\n")
    mock_docker_with_env("web", {"FOO": "bar"})

    code = main(["explain", "--file", str(compose), "web", "FOO", "--json"])
    assert code == ComposeWhyExitCode.EXPLAINED
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["schema_version"] == 1
    assert data["status"] == "explained"
    assert data["winner"]["kind"] == "service_environment"
    assert "bar" not in captured.out


def test_u31_json_mode_unknown(tmp_path: Path, capsys):
    compose = tmp_path / "compose.yaml"
    compose.write_text("services:\n  web:\n    image: busybox\n")
    mock_docker_with_env("web", {})

    code = main(["explain", "--file", str(compose), "web", "UNSET_VAR", "--json"])
    assert code == ComposeWhyExitCode.UNSUPPORTED_OR_UNKNOWN
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["schema_version"] == 1
    assert data["status"] == "unknown"


def test_u32_unusual_filename_paths(tmp_path: Path):
    weird_dir = tmp_path / "folder with spaces & symbols"
    weird_dir.mkdir()
    compose = weird_dir / "my compose file.yaml"
    compose.write_text("services:\n  web:\n    environment:\n      FOO: bar\n")
    mock_docker_with_env("web", {"FOO": "bar"})

    res = explain_variable(compose, "web", "FOO")
    assert res.status == "explained"
    assert "my compose file.yaml" in (res.winner.path or "")


def test_u36_unset_interpolation_key(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    compose = tmp_path / "compose.yaml"
    compose.write_text("services:\n  web:\n    environment:\n      TARGET: ${MISSING_VAR}\n")
    mock_docker_with_env("web", {"TARGET": ""})

    res = explain_variable(compose, "web", "TARGET")
    assert res.status == "explained"
    assert res.interpolation_source == "unresolved"
