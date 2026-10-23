"""Tests for YAML AST parsing and line number discovery."""

import pytest
from pathlib import Path
from composewhy.source_map import parse_compose_yaml
from composewhy.errors import InputError, UnsupportedError


def test_parse_literal_mapping_line(tmp_path: Path):
    compose_file = tmp_path / "compose.yaml"
    compose_file.write_text(
        "services:\n"
        "  web:\n"
        "    image: busybox\n"
        "    environment:\n"
        "      APP_MODE: production\n"
        "      PORT: 8080\n"
    )
    info = parse_compose_yaml(compose_file, "web")
    assert not info.has_unsupported_compose_feature
    assert "APP_MODE" in info.environment_mapping
    line_num, val = info.environment_mapping["APP_MODE"]
    assert line_num == 5
    assert val == "production"


def test_parse_literal_list_line(tmp_path: Path):
    compose_file = tmp_path / "compose.yaml"
    compose_file.write_text(
        "services:\n"
        "  web:\n"
        "    image: busybox\n"
        "    environment:\n"
        "      - APP_MODE=production\n"
        "      - TOKEN=a=b=c\n"
    )
    info = parse_compose_yaml(compose_file, "web")
    assert len(info.environment_list) == 2
    assert info.environment_list[0] == (5, "APP_MODE", "production")
    assert info.environment_list[1] == (6, "TOKEN", "a=b=c")


def test_parse_empty_literal_values(tmp_path: Path):
    compose_file = tmp_path / "compose.yaml"
    compose_file.write_text(
        "services:\n"
        "  web:\n"
        "    environment:\n"
        "      EMPTY_MAP: \"\"\n"
        "      - EMPTY_LIST=\n"
    )
    # Invalid YAML (mixed mapping and sequence in environment)
    with pytest.raises(InputError):
        parse_compose_yaml(compose_file, "web")


def test_duplicate_keys_detection(tmp_path: Path):
    compose_file = tmp_path / "compose.yaml"
    compose_file.write_text(
        "services:\n"
        "  web:\n"
        "    image: busybox\n"
        "    environment:\n"
        "      FOO: bar\n"
        "      FOO: baz\n"
    )
    info = parse_compose_yaml(compose_file, "web")
    assert "FOO" in info.duplicate_keys


def test_unsupported_include_construct(tmp_path: Path):
    compose_file = tmp_path / "compose.yaml"
    compose_file.write_text(
        "include:\n"
        "  - other.yaml\n"
        "services:\n"
        "  web:\n"
        "    image: busybox\n"
    )
    info = parse_compose_yaml(compose_file, "web")
    assert info.has_unsupported_compose_feature
    assert "include" in (info.unsupported_reason or "")


def test_unsupported_extends_construct(tmp_path: Path):
    compose_file = tmp_path / "compose.yaml"
    compose_file.write_text(
        "services:\n"
        "  web:\n"
        "    extends: base\n"
    )
    info = parse_compose_yaml(compose_file, "web")
    assert info.has_unsupported_compose_feature
    assert "extends" in (info.unsupported_reason or "")


def test_file_size_exceeded(tmp_path: Path):
    compose_file = tmp_path / "huge.yaml"
    compose_file.write_bytes(b"a" * (2 * 1024 * 1024 + 1))
    with pytest.raises(InputError) as exc_info:
        parse_compose_yaml(compose_file, "web")
    assert "exceeds maximum allowed size" in exc_info.value.message


def test_invalid_utf8_file(tmp_path: Path):
    compose_file = tmp_path / "invalid.yaml"
    compose_file.write_bytes(b"\xff\xfe\x00\x00")
    with pytest.raises(InputError) as exc_info:
        parse_compose_yaml(compose_file, "web")
    assert "invalid UTF-8" in exc_info.value.message
