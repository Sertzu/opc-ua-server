from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


DEFAULT_SECURITY_POLICIES = [
    "Basic256Sha256_SignAndEncrypt",
    "Basic256Sha256_Sign",
]
VALID_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


class ConfigError(ValueError):
    """Raised when the YAML configuration is invalid."""


@dataclass(slots=True)
class NodeConfig:
    node_type: str
    browse_name: str
    node_id: str | int | None = None
    value: Any = None
    variant_type: str | None = None
    writable: bool = False
    children: list["NodeConfig"] = field(default_factory=list)


@dataclass(slots=True)
class AddressSpaceConfig:
    nodes: list[NodeConfig] = field(default_factory=list)


@dataclass(slots=True)
class ServerConfig:
    endpoint: str
    name: str
    application_uri: str
    product_uri: str
    namespace_uri: str
    security_policies: list[str]


@dataclass(slots=True)
class CertificateConfig:
    root: Path
    server_certificate: Path
    server_private_key: Path
    private_key_password_env: str | None = None

    @property
    def server_dir(self) -> Path:
        return self.root / "server"

    @property
    def granted_clients_dir(self) -> Path:
        return self.root / "clients" / "granted"

    @property
    def rejected_clients_dir(self) -> Path:
        return self.root / "clients" / "rejected"

    def ensure_layout(self) -> None:
        self.server_dir.mkdir(parents=True, exist_ok=True)
        self.granted_clients_dir.mkdir(parents=True, exist_ok=True)
        self.rejected_clients_dir.mkdir(parents=True, exist_ok=True)


@dataclass(slots=True)
class AppConfig:
    source_path: Path
    logging_level: str
    asyncua_logging_level: str
    server: ServerConfig
    certificates: CertificateConfig
    address_space: AddressSpaceConfig


def load_app_config(path: Path) -> AppConfig:
    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")

    raw_data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw_data, dict):
        raise ConfigError("Top-level YAML document must be a mapping.")

    config_dir = path.resolve().parent
    logging_level = _parse_logging_level(raw_data.get("logging", {}))
    server = _parse_server_config(raw_data.get("server", {}))
    certificates = _parse_certificate_config(config_dir, raw_data.get("certificates", {}))
    address_space = _parse_address_space(raw_data.get("address_space", {}))

    return AppConfig(
        source_path=path.resolve(),
        logging_level=logging_level,
        asyncua_logging_level=_parse_asyncua_logging_level(raw_data.get("logging", {})),
        server=server,
        certificates=certificates,
        address_space=address_space,
    )


def _parse_logging_level(raw_logging: Any) -> str:
    logging_data = _require_mapping(raw_logging, "logging")
    level = str(logging_data.get("level", "INFO")).upper()
    if level not in VALID_LOG_LEVELS:
        allowed = ", ".join(sorted(VALID_LOG_LEVELS))
        raise ConfigError(f"logging.level must be one of: {allowed}")
    return level


def _parse_asyncua_logging_level(raw_logging: Any) -> str:
    logging_data = _require_mapping(raw_logging, "logging")
    level = str(logging_data.get("asyncua_level", "WARNING")).upper()
    if level not in VALID_LOG_LEVELS:
        allowed = ", ".join(sorted(VALID_LOG_LEVELS))
        raise ConfigError(f"logging.asyncua_level must be one of: {allowed}")
    return level


def _parse_server_config(raw_server: Any) -> ServerConfig:
    server_data = _require_mapping(raw_server, "server")
    endpoint = str(server_data.get("endpoint", "opc.tcp://0.0.0.0:4840/opcua/server/"))
    name = str(server_data.get("name", "Configurable AsyncUA Server"))
    application_uri = str(server_data.get("application_uri", "urn:example:configurable:opcua:server"))
    product_uri = str(server_data.get("product_uri", application_uri))
    namespace_uri = str(server_data.get("namespace_uri", f"{application_uri}:namespace"))

    raw_policies = server_data.get("security_policies", DEFAULT_SECURITY_POLICIES)
    if not isinstance(raw_policies, list) or not raw_policies:
        raise ConfigError("server.security_policies must be a non-empty list of policy names.")

    security_policies: list[str] = []
    for index, policy in enumerate(raw_policies):
        if not isinstance(policy, str):
            raise ConfigError(f"server.security_policies[{index}] must be a string.")
        if policy == "NoSecurity":
            raise ConfigError("NoSecurity is not supported in this version because it bypasses certificate trust.")
        security_policies.append(policy)

    return ServerConfig(
        endpoint=endpoint,
        name=name,
        application_uri=application_uri,
        product_uri=product_uri,
        namespace_uri=namespace_uri,
        security_policies=security_policies,
    )


def _parse_certificate_config(config_dir: Path, raw_certificates: Any) -> CertificateConfig:
    certificates_data = _require_mapping(raw_certificates, "certificates")

    root = _resolve_path(
        config_dir,
        str(certificates_data.get("root", "./certs")),
    )
    server_certificate = _resolve_path(
        root,
        str(certificates_data.get("server_certificate", "server/server_cert.pem")),
    )
    server_private_key = _resolve_path(
        root,
        str(certificates_data.get("server_private_key", "server/server_key.pem")),
    )

    private_key_password_env = certificates_data.get("private_key_password_env")
    if private_key_password_env is not None and not isinstance(private_key_password_env, str):
        raise ConfigError("certificates.private_key_password_env must be a string when provided.")

    return CertificateConfig(
        root=root,
        server_certificate=server_certificate,
        server_private_key=server_private_key,
        private_key_password_env=private_key_password_env,
    )


def _parse_address_space(raw_address_space: Any) -> AddressSpaceConfig:
    address_space_data = _require_mapping(raw_address_space, "address_space")
    raw_nodes = address_space_data.get("nodes", [])
    if not isinstance(raw_nodes, list):
        raise ConfigError("address_space.nodes must be a list.")

    nodes = [_parse_node(node_data, f"address_space.nodes[{index}]") for index, node_data in enumerate(raw_nodes)]
    return AddressSpaceConfig(nodes=nodes)


def _parse_node(raw_node: Any, location: str) -> NodeConfig:
    node_data = _require_mapping(raw_node, location)
    node_type = str(node_data.get("type", "")).strip().lower()
    if node_type not in {"folder", "object", "variable"}:
        raise ConfigError(f"{location}.type must be one of: folder, object, variable")

    browse_name = node_data.get("browse_name")
    if not isinstance(browse_name, str) or not browse_name.strip():
        raise ConfigError(f"{location}.browse_name must be a non-empty string.")

    node_id = node_data.get("node_id")
    if node_id is not None and not isinstance(node_id, (str, int)):
        raise ConfigError(f"{location}.node_id must be a string, integer, or null.")

    variant_type = node_data.get("variant_type")
    if variant_type is not None and not isinstance(variant_type, str):
        raise ConfigError(f"{location}.variant_type must be a string when provided.")

    writable = node_data.get("writable", False)
    if not isinstance(writable, bool):
        raise ConfigError(f"{location}.writable must be true or false.")

    raw_children = node_data.get("children", [])
    if not isinstance(raw_children, list):
        raise ConfigError(f"{location}.children must be a list.")
    if node_type == "variable" and raw_children:
        raise ConfigError(f"{location}.children is only valid for folder and object nodes.")

    children = [_parse_node(child, f"{location}.children[{index}]") for index, child in enumerate(raw_children)]

    return NodeConfig(
        node_type=node_type,
        browse_name=browse_name,
        node_id=node_id,
        value=node_data.get("value"),
        variant_type=variant_type,
        writable=writable,
        children=children,
    )


def _resolve_path(base: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (base / candidate).resolve()


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{name} must be a mapping.")
    return value