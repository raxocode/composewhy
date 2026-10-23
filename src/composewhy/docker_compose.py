"""Docker Compose config wrapper with strict output bounds and zero secret leakage."""

import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Callable, Tuple

from .errors import DockerError

MAX_COMPOSE_OUTPUT_BYTES = 5 * 1024 * 1024  # 5 MiB

# Global hook for test mocking
_custom_runner: Optional[Callable[[list[str], Path, int], Tuple[int, bytes, bytes]]] = None


def set_custom_compose_runner(runner: Optional[Callable[..., Any]]) -> None:
    global _custom_runner
    _custom_runner = runner


def check_docker_compose_version() -> None:
    """Verify docker compose is executable."""
    if _custom_runner is not None:
        return

    try:
        proc = subprocess.run(
            ["docker", "compose", "version", "--short"],
            shell=False,
            timeout=3,
            capture_output=True,
            text=False,
        )
        if proc.returncode != 0:
            raise DockerError("Docker Compose check failed; ensure Docker Compose v2 is installed")
    except FileNotFoundError:
        raise DockerError("Docker executable 'docker' is not available in system PATH")
    except subprocess.TimeoutExpired:
        raise DockerError("Docker Compose version check timed out")
    except Exception:
        raise DockerError("Error verifying Docker Compose availability")


def run_docker_compose_config(
    compose_path: Path,
    env_file_path: Optional[Path] = None,
    timeout: int = 10,
) -> Dict[str, Any]:
    """Execute 'docker compose config --format json' safely in memory."""
    args = ["docker", "compose", "-f", str(compose_path)]
    if env_file_path is not None:
        args += ["--env-file", str(env_file_path)]
    args += ["config", "--format", "json"]

    cwd = compose_path.parent

    if _custom_runner is not None:
        retcode, out_bytes, err_bytes = _custom_runner(args, cwd, timeout)
    else:
        check_docker_compose_version()
        try:
            proc = subprocess.Popen(
                args,
                cwd=cwd,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                out_bytes, err_bytes = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                raise DockerError(f"Docker Compose config command timed out after {timeout} seconds")
            retcode = proc.returncode
        except FileNotFoundError:
            raise DockerError("Docker executable 'docker' is not available in system PATH")
        except DockerError:
            raise
        except Exception:
            raise DockerError("Internal error executing Docker Compose subprocess")

    if len(out_bytes) > MAX_COMPOSE_OUTPUT_BYTES or len(err_bytes) > MAX_COMPOSE_OUTPUT_BYTES:
        raise DockerError("Docker Compose output exceeded 5 MiB safety limit")

    if retcode != 0:
        # Never include err_bytes in exception: might contain passwords or env values!
        raise DockerError(f"Docker Compose config failed with exit status {retcode}")

    try:
        data = json.loads(out_bytes.decode("utf-8"))
    except Exception:
        raise DockerError("Failed to parse Docker Compose config output as JSON")

    if not isinstance(data, dict):
        raise DockerError("Unexpected Docker Compose config JSON structure")

    return data
