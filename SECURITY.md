# Security Policy

## Reporting Security Vulnerabilities

The ComposeWhy team takes security and sensitive data protection seriously. If you discover a security vulnerability or potential secret leakage in ComposeWhy, please report it privately.

**Please DO NOT open a public GitHub issue.**

Instead, use **GitHub Private Vulnerability Reporting**:
1. Navigate to the repository on GitHub (`https://github.com/raxocode/composewhy`).
2. Click on the **Security** tab.
3. Click **Report a vulnerability** to submit a private report to the maintainers.

## Security Invariants

ComposeWhy is designed with the following security invariants:
- **No Value Exposure**: Secret values in YAML definitions, `.env` files, or shell variables must never be printed to standard output, standard error, JSON structures, or unhandled exception messages.
- **Safe Subprocess Handling**: Subprocess execution of `docker compose config` enforces memory limits (5 MiB budget) and strict timeout guards. In the event of a Docker Compose execution error, raw stderr streams are suppressed to avoid leaking credentials.
- **Safe YAML Parsing**: YAML parsing uses PyYAML's `SafeLoader` and explicitly avoids running any custom Python constructors or code execution.
