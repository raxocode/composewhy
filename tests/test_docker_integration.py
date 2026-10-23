"""Real Docker Compose integration tests (I01 - I06).

These tests run against an actual `docker compose config` process.
If Docker or Docker Compose is not available in the local execution environment,
the tests are gracefully skipped via pytest.skip.
In CI (GitHub Actions), Docker is available and these tests run fully.
"""

import os
import shutil
import subprocess
from pathlib import Path
import pytest

from composewhy.cli import main
from composewhy.explain import explain_variable
from composewhy.docker_compose import set_custom_compose_runner


def docker_compose_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        res = subprocess.run(
            ["docker", "compose", "version"],
            stdout=pytest.subprocess.DEVNULL if hasattr(pytest, "subprocess") else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return res.returncode == 0
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not docker_compose_available(),
        reason="Docker Compose is not available in this test environment",
    ),
]


@pytest.fixture(autouse=True)
def ensure_real_docker():
    # Clear any mock runner so real subprocess is invoked
    set_custom_compose_runner(None)
    yield
    set_custom_compose_runner(None)


def test_i01_literal_mapping(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    image: busybox\n"
        "    environment:\n"
        "      APP_PORT: '8080'\n"
    )
    res = explain_variable(compose, "web", "APP_PORT")
    assert res.status == "explained"
    assert res.winner is not None
    assert res.winner.line == 5
    assert res.winner.kind == "environment"


def test_i02_project_env_interpolation(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("PORT", raising=False)
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    image: busybox\n"
        "    environment:\n"
        "      APP_PORT: ${PORT}\n"
    )
    env_file = tmp_path / ".env"
    env_file.write_text("PORT=9000\n")

    res = explain_variable(compose, "web", "APP_PORT")
    assert res.status == "explained"
    assert res.winner is not None
    assert res.winner.kind == "environment"
    assert res.interpolation_source is not None
    assert ".env:1 (PORT)" in res.interpolation_source


def test_i03_service_env_file(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    image: busybox\n"
        "    env_file:\n"
        "      - service.env\n"
    )
    env_file = tmp_path / "service.env"
    env_file.write_text("FEATURE_FLAG=enabled\n")

    res = explain_variable(compose, "web", "FEATURE_FLAG")
    assert res.status == "explained"
    assert res.winner is not None
    assert "env_file" in res.winner.kind
    assert "service.env" in (res.winner.path or "")
    assert res.winner.line == 1


def test_i04_environment_overrides_env_file(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    image: busybox\n"
        "    env_file:\n"
        "      - service.env\n"
        "    environment:\n"
        "      DEBUG: 'true'\n"
    )
    env_file = tmp_path / "service.env"
    env_file.write_text("DEBUG=false\n")

    res = explain_variable(compose, "web", "DEBUG")
    assert res.status == "explained"
    assert res.winner is not None
    assert res.winner.kind == "environment"
    assert res.winner.line == 7
    assert len(res.candidates) == 1
    assert res.candidates[0].source.kind == "env_file"
    assert res.candidates[0].outcome == "overridden"


def test_i05_shell_overrides_project_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TAG", "shell-latest")
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    image: busybox\n"
        "    environment:\n"
        "      VERSION: ${TAG}\n"
    )
    env_file = tmp_path / ".env"
    env_file.write_text("TAG=file-fallback\n")

    res = explain_variable(compose, "web", "VERSION")
    assert res.status == "explained"
    assert res.winner is not None
    assert res.interpolation_source == "shell TAG"
    assert len(res.candidates) == 1
    assert res.candidates[0].outcome == "overridden"


def test_i06_multiple_env_files_last_wins(tmp_path: Path):
    compose = tmp_path / "compose.yaml"
    compose.write_text(
        "services:\n"
        "  web:\n"
        "    image: busybox\n"
        "    env_file:\n"
        "      - a.env\n"
        "      - b.env\n"
    )
    (tmp_path / "a.env").write_text("MODE=dev\n")
    (tmp_path / "b.env").write_text("MODE=prod\n")

    res = explain_variable(compose, "web", "MODE")
    assert res.status == "explained"
    assert res.winner is not None
    assert "b.env" in (res.winner.path or "")
    assert res.winner.line == 1
    assert len(res.candidates) == 1
    assert "a.env" in (res.candidates[0].source.path or "")
    assert res.candidates[0].outcome == "overridden"
