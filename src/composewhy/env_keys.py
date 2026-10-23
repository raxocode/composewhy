"""Env file parser that extracts key names and line numbers with zero value leakage."""

import re
from pathlib import Path
from typing import Dict, Set, Optional

from .errors import InputError, UnsupportedError

MAX_ENV_FILE_BYTES = 1024 * 1024  # 1 MiB
MAX_ENV_LINES = 100_000
IDENTIFIER_REGEX = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class EnvFileIndex:
    def __init__(self, path: Path):
        self.path = path
        self.key_lines: Dict[str, int] = {}
        self.duplicate_keys: Set[str] = set()
        self.has_unsupported_syntax: bool = False
        self.unsupported_reason: Optional[str] = None


def index_env_file(file_path: Path) -> EnvFileIndex:
    index = EnvFileIndex(file_path)

    if not file_path.exists():
        raise InputError(f"Referenced env file '{file_path}' does not exist")

    if not file_path.is_file():
        raise InputError(f"Referenced env path '{file_path}' is not a regular file")

    try:
        raw_bytes = file_path.read_bytes()
    except Exception:
        raise InputError(f"Cannot read env file '{file_path}'")

    if len(raw_bytes) > MAX_ENV_FILE_BYTES:
        raise InputError(f"Env file '{file_path}' exceeds maximum size of 1 MiB")

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise InputError(f"Env file '{file_path}' contains invalid UTF-8 bytes")

    lines = text.splitlines()
    if len(lines) > MAX_ENV_LINES:
        raise InputError(f"Env file '{file_path}' exceeds maximum line limit of {MAX_ENV_LINES}")

    for idx, raw_line in enumerate(lines):
        line_num = idx + 1
        line = raw_line.strip()

        # Ignorable lines
        if not line or line.startswith("#"):
            continue

        # Optional leading 'export '
        if line.startswith("export "):
            line = line[len("export "):].strip()

        if "=" not in line:
            # Non-standard declaration syntax
            index.has_unsupported_syntax = True
            index.unsupported_reason = f"Non-standard declaration on line {line_num} in '{file_path}'"
            continue

        raw_key, _ = line.split("=", 1)
        key = raw_key.strip()

        if not IDENTIFIER_REGEX.match(key):
            index.has_unsupported_syntax = True
            index.unsupported_reason = f"Invalid environment key format on line {line_num} in '{file_path}'"
            continue

        if key in index.key_lines:
            index.duplicate_keys.add(key)
        else:
            index.key_lines[key] = line_num

    return index
