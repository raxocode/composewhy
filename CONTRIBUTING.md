# Contributing to ComposeWhy

Thank you for your interest in contributing to ComposeWhy! We appreciate bug reports, documentation improvements, and pull requests.

## Core Project Invariants

When contributing code, you must strictly uphold the core security and functional invariants:
1. **Zero Secret Leakage**: Never print, log, serialize, or expose environment variable values. All values must remain `[REDACTED]`.
2. **Read-Only Diagnostics**: Never run, build, mutate, or stop Docker containers. ComposeWhy only reads compose files and invokes `docker compose config` in memory.
3. **Conservative Unknowns**: If a Compose construct or interpolation pattern cannot be deterministically and accurately mapped to a source line, return `status=unknown` (exit code 3) rather than guessing.
4. **No Unneeded Dependencies**: Keep dependencies minimal (`PyYAML`, standard library). No node, rust, or web frameworks.

## Submitting Issues and Bug Reports

- Always use the GitHub Issue Template for bug reports.
- **NEVER paste real secrets, database passwords, or production credentials in bug reports.**
- Provide a minimal, sanitized reproduction fixture (`compose.yaml` and `.env.example`).
- State expected provenance vs observed outcome.

## Development Workflow

1. Clone the repository:
   ```bash
   git clone https://github.com/raxocode/composewhy.git
   cd composewhy
   ```
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Install editable package with test dependencies:
   ```bash
   python -m pip install -e ".[test]"
   ```
4. Run tests:
   ```bash
   python -m pytest -v
   ```
5. Ensure all unit and secret redaction tests pass before opening a Pull Request.
