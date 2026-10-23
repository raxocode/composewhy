# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-23

### Added
- Core `composewhy` CLI tool (`explain` and `version` subcommands).
- Deterministic provenance engine tracing Docker Compose environment variables to source files and line numbers.
- Distinguishes container variable winner from interpolation input source.
- Support for service `environment` mapping (`KEY: val`) and list (`- KEY=val`) forms.
- Support for service `env_file` scalar and sequence formats with last-file-wins precedence.
- Support for project `.env` file interpolation and shell environment overrides.
- Zero secret-value leakage guarantee: secrets are masked as `[REDACTED]` in terminal, JSON, and errors.
- Clean JSON output mode (`--json`) for automated agents and scripts.
- Memory and file size safety caps (2 MiB YAML parse cap, 1 MiB env file cap, 5 MiB Docker output cap, 30s timeout cap).
- Comprehensive test suite covering 36 unit cases (U01-U36), secret redaction tests, and Docker integration tests (I01-I06).

### Deliberate Limitations
- Single Compose YAML file input per command (no multi-file merge in v0.1).
- Unsupported features (YAML `include`/`extends`, merge keys `<<`, complex expansions `${FOO:-default}`) conservatively return status `unknown` / exit code 3.
- No inspection of remote Docker image `ENV` layers or running containers.
