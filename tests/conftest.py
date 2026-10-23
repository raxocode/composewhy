"""Pytest configuration and test fixtures."""

import os
import shutil
import pytest
from pathlib import Path

from composewhy.docker_compose import set_custom_compose_runner


@pytest.fixture(autouse=True)
def reset_compose_runner():
    """Ensure custom mock runner is reset after every test."""
    yield
    set_custom_compose_runner(None)


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Provide a temporary directory for test fixtures."""
    return tmp_path


def mock_docker_with_env(service_name: str, env_dict: dict):
    """Helper to mock docker compose output with given service environment."""
    import json
    def runner(args, cwd, timeout):
        output = json.dumps({"services": {service_name: {"environment": env_dict}}}).encode("utf-8")
        return (0, output, b"")
    set_custom_compose_runner(runner)
