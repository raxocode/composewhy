"""Safe YAML source AST parser with line number mapping and security safeguards."""

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import yaml

from .errors import InputError, UnsupportedError

MAX_YAML_BYTES = 2 * 1024 * 1024  # 2 MiB


class ServiceAstInfo:
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.environment_mapping: Dict[str, Tuple[int, str]] = {}  # key -> (line, raw_expr)
        self.environment_list: List[Tuple[int, str, str]] = []     # [(line, key, raw_expr)]
        self.env_files: List[Tuple[int, str]] = []                 # [(line, path_str)]
        self.has_unsupported_compose_feature: bool = False
        self.unsupported_reason: Optional[str] = None
        self.duplicate_keys: List[str] = []


def _check_mapping_for_duplicates(node: yaml.MappingNode, path_label: str) -> None:
    seen = set()
    for key_node, _ in node.value:
        if isinstance(key_node, yaml.ScalarNode):
            key = key_node.value
            if key in seen:
                raise InputError(f"Duplicate key '{key}' detected in {path_label}")
            seen.add(key)


def _check_for_aliases_and_merges(k_node: yaml.ScalarNode, v_node: yaml.MappingNode, text: str) -> bool:
    """Check if target service contains or was created with aliases, merge keys, or custom tags."""
    service_start = k_node.start_mark.line
    service_end = v_node.end_mark.line

    # If the service mapping definition line is before the service key line,
    # it means v_node was an alias pointing to an anchor defined earlier
    if v_node.start_mark.line < service_start:
        return True

    # Check for AliasToken within the service line span
    try:
        for token in yaml.scan(text, Loader=yaml.SafeLoader):
            if isinstance(token, yaml.tokens.AliasToken):
                if service_start <= token.start_mark.line <= service_end:
                    return True
    except Exception:
        pass

    # Check for merge keys (<<) or custom tags in the service subtree
    def check_node(node: yaml.Node) -> bool:
        if node.tag and not node.tag.startswith("tag:yaml.org,2002:"):
            return True
        if isinstance(node, yaml.MappingNode):
            for kn, vn in node.value:
                if isinstance(kn, yaml.ScalarNode) and kn.value == "<<":
                    return True
                if check_node(kn) or check_node(vn):
                    return True
        elif isinstance(node, yaml.SequenceNode):
            for item in node.value:
                if check_node(item):
                    return True
        return False

    return check_node(v_node)


def parse_compose_yaml(file_path: Path, target_service: str) -> ServiceAstInfo:
    if not file_path.is_file():
        raise InputError(f"Compose file '{file_path}' does not exist or is not a regular file")

    try:
        raw_bytes = file_path.read_bytes()
    except Exception:
        raise InputError(f"Cannot read Compose file '{file_path}'")

    if len(raw_bytes) > MAX_YAML_BYTES:
        raise InputError(f"Compose file '{file_path}' exceeds maximum allowed size of 2 MiB")

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise InputError(f"Compose file '{file_path}' contains invalid UTF-8 bytes")

    try:
        root_node = yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.YAMLError:
        raise InputError(f"Compose file '{file_path}' contains invalid YAML syntax")

    if root_node is None:
        raise InputError(f"Compose file '{file_path}' is empty")

    if not isinstance(root_node, yaml.MappingNode):
        raise InputError(f"Root of Compose file '{file_path}' must be a YAML mapping")

    _check_mapping_for_duplicates(root_node, "root")

    services_node: Optional[yaml.MappingNode] = None

    for k_node, v_node in root_node.value:
        if isinstance(k_node, yaml.ScalarNode):
            if k_node.value == "include":
                # Top-level include is unsupported in v0.1
                info = ServiceAstInfo(target_service)
                info.has_unsupported_compose_feature = True
                info.unsupported_reason = "The Compose file uses unsupported top-level construct: 'include'."
                return info
            if k_node.value == "services":
                if not isinstance(v_node, yaml.MappingNode):
                    raise InputError(f"'services' in '{file_path}' must be a YAML mapping")
                services_node = v_node

    if services_node is None:
        raise InputError(f"No 'services' mapping found in '{file_path}'")

    _check_mapping_for_duplicates(services_node, "services")

    target_k_node: Optional[yaml.ScalarNode] = None
    target_service_node: Optional[yaml.MappingNode] = None

    for k_node, v_node in services_node.value:
        if isinstance(k_node, yaml.ScalarNode) and k_node.value == target_service:
            target_k_node = k_node
            if not isinstance(v_node, yaml.MappingNode):
                raise InputError(f"Service '{target_service}' must be a mapping in '{file_path}'")
            target_service_node = v_node
            break

    if target_service_node is None or target_k_node is None:
        raise InputError(f"Service '{target_service}' not found in '{file_path}'")

    info = ServiceAstInfo(target_service)

    # Check for aliases or merge keys affecting the target service
    if _check_for_aliases_and_merges(target_k_node, target_service_node, text):
        info.has_unsupported_compose_feature = True
        info.unsupported_reason = (
            f"Service '{target_service}' uses YAML aliases or merge keys, which are unsupported in v0.1."
        )
        return info

    _check_mapping_for_duplicates(target_service_node, f"service '{target_service}'")

    for k_node, v_node in target_service_node.value:
        if not isinstance(k_node, yaml.ScalarNode):
            continue

        key_name = k_node.value

        if key_name in ("extends", "include"):
            info.has_unsupported_compose_feature = True
            info.unsupported_reason = (
                f"Service '{target_service}' uses unsupported Compose feature: '{key_name}'."
            )
            return info

        if key_name == "environment":
            if isinstance(v_node, yaml.MappingNode):
                # Mapping form: KEY: VALUE
                seen_env_keys = set()
                for env_k_node, env_v_node in v_node.value:
                    if isinstance(env_k_node, yaml.ScalarNode):
                        env_k = env_k_node.value
                        if env_k in seen_env_keys:
                            info.duplicate_keys.append(env_k)
                        seen_env_keys.add(env_k)

                        line_num = env_k_node.start_mark.line + 1
                        raw_val = env_v_node.value if isinstance(env_v_node, yaml.ScalarNode) else ""
                        if env_v_node.tag == "tag:yaml.org,2002:null" or (isinstance(env_v_node, yaml.ScalarNode) and env_v_node.value is None):
                            raw_val = None
                        info.environment_mapping[env_k] = (line_num, raw_val)
            elif isinstance(v_node, yaml.SequenceNode):
                # List form: - KEY=VALUE or - KEY
                seen_env_keys = set()
                for item_node in v_node.value:
                    if isinstance(item_node, yaml.ScalarNode):
                        line_num = item_node.start_mark.line + 1
                        entry_str = item_node.value or ""
                        if "=" in entry_str:
                            k, v = entry_str.split("=", 1)
                            if k in seen_env_keys:
                                info.duplicate_keys.append(k)
                            seen_env_keys.add(k)
                            info.environment_list.append((line_num, k, v))
                        else:
                            # Bare list item without = (e.g. - KEY)
                            if entry_str in seen_env_keys:
                                info.duplicate_keys.append(entry_str)
                            seen_env_keys.add(entry_str)
                            info.environment_list.append((line_num, entry_str, None))
            else:
                info.has_unsupported_compose_feature = True
                info.unsupported_reason = f"Service '{target_service}' environment must be a mapping or list."
                return info

        elif key_name == "env_file":
            if isinstance(v_node, yaml.ScalarNode):
                line_num = v_node.start_mark.line + 1
                info.env_files.append((line_num, v_node.value))
            elif isinstance(v_node, yaml.SequenceNode):
                for item_node in v_node.value:
                    if isinstance(item_node, yaml.ScalarNode):
                        line_num = item_node.start_mark.line + 1
                        info.env_files.append((line_num, item_node.value))
                    else:
                        info.has_unsupported_compose_feature = True
                        info.unsupported_reason = (
                            f"Service '{target_service}' env_file entries must be scalar path strings."
                        )
                        return info
            else:
                info.has_unsupported_compose_feature = True
                info.unsupported_reason = (
                    f"Service '{target_service}' env_file must be a path string or sequence of path strings."
                )
                return info

    return info
