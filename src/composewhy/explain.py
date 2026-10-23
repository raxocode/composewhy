"""Core deterministic provenance explanation engine."""

import os
import re
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from .models import ExplainResult, SourceRef, Candidate
from .source_map import parse_compose_yaml, ServiceAstInfo
from .env_keys import index_env_file, EnvFileIndex
from .docker_compose import run_docker_compose_config
from .errors import ComposeWhyExitCode, InputError, UnsupportedError

IDENTIFIER_REGEX = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
STRICT_INTERPOLATION_REGEX = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def _get_relative_path(path: Path, base_dir: Path) -> str:
    try:
        return str(path.relative_to(base_dir))
    except ValueError:
        return str(path)


def explain_variable(
    compose_path: Path,
    service_name: str,
    variable_name: str,
    env_file_path: Optional[Path] = None,
    timeout: int = 10,
) -> ExplainResult:
    # 1. Validate variable name
    if not IDENTIFIER_REGEX.match(variable_name):
        raise InputError(f"Invalid variable name '{variable_name}'; must match '^[A-Za-z_][A-Za-z0-9_]*$'")

    compose_path = compose_path.resolve()
    base_dir = compose_path.parent
    rel_compose_path = _get_relative_path(compose_path, Path.cwd())

    # 2. Parse YAML AST
    ast_info: ServiceAstInfo = parse_compose_yaml(compose_path, service_name)

    if ast_info.has_unsupported_compose_feature:
        return ExplainResult(
            service=service_name,
            variable=variable_name,
            status="unknown",
            effective_presence="unknown",
            reason_code="UNSUPPORTED_COMPOSE_FEATURE",
            explanation=ast_info.unsupported_reason or "Service uses unsupported Compose feature.",
            exit_code=ComposeWhyExitCode.UNSUPPORTED_OR_UNKNOWN,
        )

    if variable_name in ast_info.duplicate_keys:
        return ExplainResult(
            service=service_name,
            variable=variable_name,
            status="unknown",
            effective_presence="unknown",
            reason_code="DUPLICATE_KEY",
            explanation=f"Variable '{variable_name}' is declared multiple times in service '{service_name}' environment.",
            exit_code=ComposeWhyExitCode.UNSUPPORTED_OR_UNKNOWN,
        )

    # 3. Resolve confirmed project .env file (for interpolation)
    project_env_index: Optional[EnvFileIndex] = None
    target_project_env_path: Optional[Path] = None

    if env_file_path is not None:
        target_project_env_path = env_file_path.resolve()
        project_env_index = index_env_file(target_project_env_path)
    else:
        default_env = base_dir / ".env"
        if default_env.is_file():
            target_project_env_path = default_env
            project_env_index = index_env_file(default_env)

    # 4. Run Docker Compose config
    resolved_config = run_docker_compose_config(
        compose_path=compose_path,
        env_file_path=target_project_env_path,
        timeout=timeout,
    )

    # Verify target service in resolved config
    services_dict = resolved_config.get("services", {})
    if not isinstance(services_dict, dict) or service_name not in services_dict:
        raise InputError(f"Service '{service_name}' not found in Docker Compose resolved model")

    svc_model = services_dict[service_name]
    effective_env: Dict[str, Any] = {}
    raw_env_model = svc_model.get("environment")

    if isinstance(raw_env_model, dict):
        effective_env = raw_env_model
    elif isinstance(raw_env_model, list):
        for item in raw_env_model:
            if isinstance(item, str) and "=" in item:
                k, v = item.split("=", 1)
                effective_env[k] = v

    is_present_in_docker = variable_name in effective_env

    # 5. Check direct service 'environment'
    raw_env_entry: Optional[Tuple[int, Optional[str]]] = None

    if variable_name in ast_info.environment_mapping:
        raw_env_entry = ast_info.environment_mapping[variable_name]
    else:
        for line_num, k, v in ast_info.environment_list:
            if k == variable_name:
                raw_env_entry = (line_num, v)
                break

    candidates: List[Candidate] = []

    if raw_env_entry is not None:
        line_num, raw_val = raw_env_entry

        # Null check
        if raw_val is None:
            # Check if bare list or explicit null
            if raw_val is None and not any(k == variable_name and v is None for _, k, v in ast_info.environment_list):
                return ExplainResult(
                    service=service_name,
                    variable=variable_name,
                    status="unknown",
                    effective_presence="unknown",
                    reason_code="UNSUPPORTED_NULL_ENV",
                    explanation=f"Service '{service_name}' defines '{variable_name}: null', which is unsupported in v0.1.",
                    exit_code=ComposeWhyExitCode.UNSUPPORTED_OR_UNKNOWN,
                )
            else:
                return ExplainResult(
                    service=service_name,
                    variable=variable_name,
                    status="unknown",
                    effective_presence="unknown",
                    reason_code="UNSUPPORTED_PASS_THROUGH",
                    explanation=f"Service '{service_name}' defines bare environment pass-through entry for '{variable_name}', which is unsupported in v0.1.",
                    exit_code=ComposeWhyExitCode.UNSUPPORTED_OR_UNKNOWN,
                )

        # Check for complex/unsupported interpolation
        if "$" in raw_val:
            match = STRICT_INTERPOLATION_REGEX.match(raw_val)
            if not match:
                return ExplainResult(
                    service=service_name,
                    variable=variable_name,
                    status="unknown",
                    effective_presence="unknown",
                    reason_code="UNSUPPORTED_INTERPOLATION",
                    explanation=f"Service '{service_name}' uses unsupported or complex variable interpolation in '{variable_name}'.",
                    exit_code=ComposeWhyExitCode.UNSUPPORTED_OR_UNKNOWN,
                )

            interpolated_var = match.group(1)

            # Determine interpolation source: shell vs project .env
            shell_has_var = interpolated_var in os.environ
            env_file_has_var = False
            env_file_line: Optional[int] = None

            if project_env_index and interpolated_var in project_env_index.key_lines:
                env_file_has_var = True
                env_file_line = project_env_index.key_lines[interpolated_var]

            interpolation_source: Optional[str] = None

            if shell_has_var:
                interpolation_source = "shell"
                if env_file_has_var and target_project_env_path:
                    candidates.append(
                        Candidate(
                            source=SourceRef(
                                kind="project_env",
                                path=_get_relative_path(target_project_env_path, Path.cwd()),
                                line=env_file_line,
                                key=interpolated_var,
                            ),
                            outcome="overridden",
                            note=f"did not supply interpolation; shell has precedence for {interpolated_var}",
                        )
                    )
            elif env_file_has_var:
                interpolation_source = f"project_env"
                if target_project_env_path:
                    candidates.append(
                        Candidate(
                            source=SourceRef(
                                kind="project_env",
                                path=_get_relative_path(target_project_env_path, Path.cwd()),
                                line=env_file_line,
                                key=interpolated_var,
                            ),
                            outcome="winner",
                            note=f"supplied interpolation for {interpolated_var}",
                        )
                    )
            else:
                interpolation_source = "unresolved"

            winner_ref = SourceRef(
                kind="service_environment",
                path=rel_compose_path,
                line=line_num,
                key=variable_name,
            )

            # Verify against Docker Compose canonical model
            if not is_present_in_docker:
                return ExplainResult(
                    service=service_name,
                    variable=variable_name,
                    status="unknown",
                    effective_presence="absent",
                    reason_code="INCONSISTENT_RESOLUTION",
                    explanation="Raw Compose declares variable, but Docker Compose resolved model does not contain it.",
                    exit_code=ComposeWhyExitCode.UNSUPPORTED_OR_UNKNOWN,
                )

            interp_desc = f"shell {interpolated_var}" if interpolation_source == "shell" else (
                f"{_get_relative_path(target_project_env_path, Path.cwd())}:{env_file_line} ({interpolated_var})"
                if interpolation_source == "project_env" and target_project_env_path else "unresolved"
            )

            explanation = (
                f"The service declares {variable_name} through environment. "
                f"The {interpolation_source} supplied {interpolated_var} during Compose interpolation."
            )

            return ExplainResult(
                service=service_name,
                variable=variable_name,
                status="explained",
                effective_presence="present",
                winner=winner_ref,
                interpolation_source=interp_desc,
                candidates=candidates,
                reason_code="ENVIRONMENT_INTERPOLATED",
                explanation=explanation,
                exit_code=ComposeWhyExitCode.EXPLAINED,
            )

        # Literal value
        winner_ref = SourceRef(
            kind="service_environment",
            path=rel_compose_path,
            line=line_num,
            key=variable_name,
        )

        # Note any overridden env_file definitions
        for env_file_line, env_file_rel in ast_info.env_files:
            if "$" in env_file_rel or "{" in env_file_rel:
                continue
            resolved_env_path = (base_dir / env_file_rel).resolve()
            if resolved_env_path.is_file():
                idx = index_env_file(resolved_env_path)
                if variable_name in idx.key_lines:
                    candidates.append(
                        Candidate(
                            source=SourceRef(
                                kind="service_env_file",
                                path=_get_relative_path(resolved_env_path, Path.cwd()),
                                line=idx.key_lines[variable_name],
                                key=variable_name,
                            ),
                            outcome="overridden",
                            note="service environment takes precedence over env_file",
                        )
                    )

        if not is_present_in_docker:
            return ExplainResult(
                service=service_name,
                variable=variable_name,
                status="unknown",
                effective_presence="absent",
                reason_code="INCONSISTENT_RESOLUTION",
                explanation="Raw Compose declares variable, but Docker Compose resolved model does not contain it.",
                exit_code=ComposeWhyExitCode.UNSUPPORTED_OR_UNKNOWN,
            )

        return ExplainResult(
            service=service_name,
            variable=variable_name,
            status="explained",
            effective_presence="present",
            winner=winner_ref,
            interpolation_source=None,
            candidates=candidates,
            reason_code="SERVICE_ENVIRONMENT_LITERAL",
            explanation=f"The service declares {variable_name} directly in Compose environment.",
            exit_code=ComposeWhyExitCode.EXPLAINED,
        )

    # 6. Check service 'env_file' list
    env_file_definitions: List[Tuple[Path, int]] = []

    for env_file_line_in_yaml, env_file_rel in ast_info.env_files:
        if "$" in env_file_rel or "{" in env_file_rel or "}" in env_file_rel:
            return ExplainResult(
                service=service_name,
                variable=variable_name,
                status="unknown",
                effective_presence="unknown",
                reason_code="UNSUPPORTED_COMPOSE_FEATURE",
                explanation=f"Interpolated or dynamic env_file path '{env_file_rel}' is unsupported in v0.1.",
                exit_code=ComposeWhyExitCode.UNSUPPORTED_OR_UNKNOWN,
            )

        resolved_env_path = (base_dir / env_file_rel).resolve()
        if not resolved_env_path.is_file():
            raise InputError(f"Referenced env_file '{env_file_rel}' does not exist or is unreadable")

        idx = index_env_file(resolved_env_path)
        if variable_name in idx.duplicate_keys:
            return ExplainResult(
                service=service_name,
                variable=variable_name,
                status="unknown",
                effective_presence="unknown",
                reason_code="DUPLICATE_KEY_IN_ENV_FILE",
                explanation=f"Env file '{env_file_rel}' has duplicate entries for '{variable_name}'.",
                exit_code=ComposeWhyExitCode.UNSUPPORTED_OR_UNKNOWN,
            )

        if variable_name in idx.key_lines:
            env_file_definitions.append((resolved_env_path, idx.key_lines[variable_name]))

    if env_file_definitions:
        # The last file defining the key wins
        winning_path, winning_line = env_file_definitions[-1]
        winner_ref = SourceRef(
            kind="service_env_file",
            path=_get_relative_path(winning_path, Path.cwd()),
            line=winning_line,
            key=variable_name,
        )

        for p, l in env_file_definitions[:-1]:
            candidates.append(
                Candidate(
                    source=SourceRef(
                        kind="service_env_file",
                        path=_get_relative_path(p, Path.cwd()),
                        line=l,
                        key=variable_name,
                    ),
                    outcome="overridden",
                    note="overridden by later env_file in service definition",
                )
            )

        if not is_present_in_docker:
            return ExplainResult(
                service=service_name,
                variable=variable_name,
                status="unknown",
                effective_presence="absent",
                reason_code="INCONSISTENT_RESOLUTION",
                explanation="Env file declares variable, but Docker Compose resolved model does not contain it.",
                exit_code=ComposeWhyExitCode.UNSUPPORTED_OR_UNKNOWN,
            )

        return ExplainResult(
            service=service_name,
            variable=variable_name,
            status="explained",
            effective_presence="present",
            winner=winner_ref,
            candidates=candidates,
            reason_code="SERVICE_ENV_FILE",
            explanation=f"The variable is supplied by service env_file '{_get_relative_path(winning_path, Path.cwd())}'.",
            exit_code=ComposeWhyExitCode.EXPLAINED,
        )

    # 7. Variable not declared in service environment or env_file
    if project_env_index and variable_name in project_env_index.key_lines:
        candidates.append(
            Candidate(
                source=SourceRef(
                    kind="project_env",
                    path=_get_relative_path(target_project_env_path, Path.cwd()) if target_project_env_path else ".env",
                    line=project_env_index.key_lines[variable_name],
                    key=variable_name,
                ),
                outcome="unused",
                note="did not inject into container; project .env alone does not inject without service declaration",
            )
        )

    if is_present_in_docker:
        # Key is present in docker config, but not in our analyzed sources
        return ExplainResult(
            service=service_name,
            variable=variable_name,
            status="unknown",
            effective_presence="present",
            candidates=candidates,
            reason_code="UNATTRIBUTED_EFFECTIVE_VALUE",
            explanation=f"Variable '{variable_name}' is present in Docker Compose model but could not be attributed to direct environment or env_file.",
            exit_code=ComposeWhyExitCode.UNSUPPORTED_OR_UNKNOWN,
        )

    return ExplainResult(
        service=service_name,
        variable=variable_name,
        status="unknown",
        effective_presence="unknown",
        candidates=candidates,
        reason_code="POSSIBLE_IMAGE_ENV",
        explanation=(
            f"The service does not declare '{variable_name}' in Compose environment or env_file. "
            f"A project .env key alone does not inject a variable into a container. "
            f"If present at runtime, it may be defined in the image Dockerfile ENV."
        ),
        exit_code=ComposeWhyExitCode.UNSUPPORTED_OR_UNKNOWN,
    )
