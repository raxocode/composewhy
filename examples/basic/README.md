# Basic Example

This fixture demonstrates Docker Compose environment variable provenance tracking with `${DB_URL}` interpolation.

## Files
- `compose.yaml`: Service definition with `DATABASE_URL: ${DB_URL}`.
- `.env.example`: Sample project environment file. Copy to `.env` to test.

## Running ComposeWhy

```bash
cp .env.example .env
composewhy explain --file compose.yaml web DATABASE_URL
```
