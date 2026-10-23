# ComposeWhy

Find which Docker Compose file or environment source supplied a variable — with sensitive values redacted.

ComposeWhy is a local, read-only diagnostics CLI for Docker Compose developers. It explains exactly which configuration source (YAML literal, service `env_file`, project `.env`, or shell environment) supplied a container's environment variable, which sources were overridden, and why — without printing secret values or starting containers.

## Quick Example

```yaml
# compose.yaml
services:
  web:
    image: busybox
    environment:
      DATABASE_URL: ${DB_URL}
```

```bash
# Run provenance diagnostics
composewhy explain --file compose.yaml web DATABASE_URL
```

ComposeWhy reports that `DATABASE_URL` is assigned on line 5 of `compose.yaml` and that the interpolation variable `DB_URL` was resolved from your project `.env` or shell. Secret values remain `[REDACTED]`.

## Installation

Install directly from GitHub into a virtual environment or with `pipx`:

```bash
python -m pip install 'git+https://github.com/raxocode/composewhy.git@v0.1.0'
```

Verify the installation:

```bash
composewhy version
composewhy --help
```

For development:

```bash
git clone https://github.com/raxocode/composewhy.git
cd composewhy
python -m pip install -e .
```

*Note: Python 3.11+ and Docker Compose v2 are supported. No npm or Node.js runtime is required.*

## Usage and Verified Output

Given a standard Docker Compose service with environment interpolation:

```yaml
# compose.yaml
services:
  web:
    image: busybox
    environment:
      DATABASE_URL: ${DB_URL}
```

```text
# .env (local project environment file)
DB_URL=postgres://user:password@db.local:5432/app
```

Running ComposeWhy:

```bash
composewhy explain --file compose.yaml --env-file .env web DATABASE_URL
```

Output:

```text
ComposeWhy 0.1.0
SERVICE   web
VARIABLE  DATABASE_URL
STATUS    EXPLAINED

WINNER
  compose.yaml:5 — service_environment.DATABASE_URL
  Interpolation input: .env:1 (DB_URL)
  Value: [REDACTED]

OVERRIDDEN OR UNUSED
  .env:1 — DB_URL (supplied interpolation for DB_URL)

WHY
  The service declares DATABASE_URL through environment. The project_env supplied DB_URL during Compose interpolation.
```

## Meaning of Candidate Outcomes

| Outcome | Definition |
|---|---|
| **WINNER** | The configuration source whose entry supplied the effective variable to the container. |
| **OVERRIDDEN** | A candidate source defined this variable, but a higher-precedence rule overrode it (e.g. `environment` overriding `env_file`, or shell overriding `.env`). |
| **UNUSED** | The source defined the variable, but Compose does not inject it into this service (e.g., project `.env` without corresponding `${VAR}` or `env_file`). |
| **UNKNOWN** | The provenance cannot be determined with mathematical certainty in v0.1 (e.g., unsupported Compose feature or ambiguous configuration). |

## Supported v0.1 Matrix and Limitations

### Supported in v0.1
- Single compose YAML file (`compose.yaml`, `docker-compose.yml`, or specified path).
- Service `environment` in mapping format (`KEY: value`) and list format (`- KEY=value`).
- Service `env_file` scalar string or sequence of files with strict last-file-wins precedence.
- Project-level `.env` file (default `.env` or `--env-file`).
- Direct `${VAR}` interpolation traced to shell environment or project `.env`.
- Value masking and redaction across human output, JSON output, and all error paths.

### Deliberate Limitations (Returns `UNKNOWN` or error)
- Multiple Compose file merges (`-f f1.yml -f f2.yml`).
- Compose `include` and `extends` directives.
- Complex shell expansions (`${VAR:-default}`, `${VAR:+alternate}`, nested expansions).
- Docker image `ENV` layer inspection (does not inspect remote registry images).
- Running container inspection (ComposeWhy does not run or attach to containers).

## Security and Privacy Invariants

- **Zero Value Leakage**: ComposeWhy NEVER prints secret values, tokens, or passwords to stdout, stderr, JSON, or exception logs. Values are strictly displayed as `[REDACTED]`.
- **Read-Only Operation**: ComposeWhy NEVER builds, creates, starts, stops, or modifies Docker containers.
- **Offline & Local**: No network requests, telemetry, or remote analytics.

## JSON Output for Scripts and Agents

Pass `--json` to produce machine-readable, schema-validated JSON:

```bash
composewhy explain --file compose.yaml --json web DATABASE_URL
```

```json
{
  "schema_version": 1,
  "product_version": "0.1.0",
  "service": "web",
  "variable": "DATABASE_URL",
  "status": "explained",
  "effective_presence": "present",
  "winner": {
    "kind": "service_environment",
    "path": "compose.yaml",
    "line": 5,
    "interpolation_source": ".env:1 (DB_URL)"
  },
  "candidates": [
    {
      "kind": "project_env",
      "path": ".env",
      "line": 1,
      "outcome": "winner",
      "note": "supplied interpolation for DB_URL"
    }
  ],
  "reason_code": "ENVIRONMENT_INTERPOLATED",
  "explanation": "The service declares DATABASE_URL through environment. The project_env supplied DB_URL during Compose interpolation.",
  "warnings": []
}
```

Exit codes:
- `0`: Explained (`status=explained`)
- `2`: CLI usage / argument error
- `3`: Unsupported feature or ambiguous (`status=unknown`)
- `4`: Input error (unreadable file, invalid YAML syntax, missing service)
- `5`: Docker Compose command failure or timeout
- `6`: Internal error

## Running Tests and Local Build

ComposeWhy uses standard `pytest` and Python `build`:

```bash
# Install dependencies
python -m pip install -e ".[test]"

# Run unit and secret redaction tests
python -m pytest -v

# Run including live Docker Compose integration tests (requires local Docker)
python -m pytest -v --run-integration

# Build sdist and wheel packages
python -m build
```

## Contributing and Bug Reports

We welcome contributions and bug reports!
- Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting pull requests.
- When filing a bug report via GitHub Issues, use the provided bug template and **NEVER paste real secrets, API keys, or actual credentials**. Always sanitize your YAML and env files.
- For security issues, refer to [SECURITY.md](SECURITY.md).

## License

MIT License. Copyright (c) 2026 RaxoCode. See [LICENSE](LICENSE) for details.
