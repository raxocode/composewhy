"""Tests for env file key indexing and line discovery."""

import pytest
from pathlib import Path
from composewhy.env_keys import index_env_file
from composewhy.errors import InputError


def test_index_normal_env_file(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# Comment line\n"
        "\n"
        "DB_HOST=localhost\n"
        "export DB_PORT=5432\n"
        "DB_PASS=secret#notcomment\n"
    )
    idx = index_env_file(env_file)
    assert not idx.has_unsupported_syntax
    assert idx.key_lines.get("DB_HOST") == 3
    assert idx.key_lines.get("DB_PORT") == 4
    assert idx.key_lines.get("DB_PASS") == 5


def test_index_duplicate_keys(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "VAR=first\n"
        "VAR=second\n"
    )
    idx = index_env_file(env_file)
    assert "VAR" in idx.duplicate_keys


def test_index_unsupported_syntax(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("NOT_VALID_KEY_DECLARATION\n")
    idx = index_env_file(env_file)
    assert idx.has_unsupported_syntax


def test_env_file_missing(tmp_path: Path):
    with pytest.raises(InputError):
        index_env_file(tmp_path / "nonexistent.env")


def test_env_file_too_large(tmp_path: Path):
    huge_file = tmp_path / "huge.env"
    huge_file.write_bytes(b"A=1\n" * 300_000)  # > 1 MiB
    with pytest.raises(InputError) as exc_info:
        index_env_file(huge_file)
    assert "exceeds maximum size" in exc_info.value.message
