from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence

from asyncua import Server, ua

from .certificates import ManualTrustCertificateValidator
from .config import AppConfig, ConfigError, NodeConfig, load_app_config


LOGGER = logging.getLogger(__name__)
APP_VERSION = "0.1.0"
SECURITY_POLICY_MAP = {
    "Basic256Sha256_Sign": ua.SecurityPolicyType.Basic256Sha256_Sign,
    "Basic256Sha256_SignAndEncrypt": ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt,
    "Aes128Sha256RsaOaep_Sign": ua.SecurityPolicyType.Aes128Sha256RsaOaep_Sign,
    "Aes128Sha256RsaOaep_SignAndEncrypt": ua.SecurityPolicyType.Aes128Sha256RsaOaep_SignAndEncrypt,
    "Aes256Sha256RsaPss_Sign": ua.SecurityPolicyType.Aes256Sha256RsaPss_Sign,
    "Aes256Sha256RsaPss_SignAndEncrypt": ua.SecurityPolicyType.Aes256Sha256RsaPss_SignAndEncrypt,
}


async def build_server(config: AppConfig) -> Server:
    config.certificates.ensure_layout()
    _validate_server_certificate_files(config)

    server = Server()
    await server.init()
    server.application_type = ua.ApplicationType.Server
    server.product_uri = config.server.product_uri
    server.set_endpoint(config.server.endpoint)
    server.set_server_name(config.server.name)
    await server.set_application_uri(config.server.application_uri)
    await server.set_build_info(
        product_uri=config.server.product_uri,
        manufacturer_name=config.server.name,
        product_name=config.server.name,
        software_version=APP_VERSION,
        build_number="0",
        build_date=datetime.now(),
    )

    await server.load_certificate(config.certificates.server_certificate)
    await server.load_private_key(
        config.certificates.server_private_key,
        password=_private_key_password(config),
    )

    security_policies = _resolve_security_policies(config.server.security_policies)
    server.set_security_policy(security_policies)
    server.set_identity_tokens([ua.AnonymousIdentityToken])
    server.iserver.certificate_validator = ManualTrustCertificateValidator(
        granted_dir=config.certificates.granted_clients_dir,
        rejected_dir=config.certificates.rejected_clients_dir,
    )

    namespace_index = await server.register_namespace(config.server.namespace_uri)
    await populate_address_space(server, namespace_index, config.address_space.nodes)
    return server


async def populate_address_space(server: Server, namespace_index: int, nodes: list[NodeConfig]) -> None:
    for node in nodes:
        await _add_configured_node(server.nodes.objects, namespace_index, node, ())


async def run_server(config: AppConfig) -> None:
    server = await build_server(config)
    shutdown_event = asyncio.Event()
    _install_signal_handlers(shutdown_event)

    LOGGER.info("Starting OPC UA server on %s", config.server.endpoint)
    LOGGER.info("Granted client certificates directory: %s", config.certificates.granted_clients_dir)
    LOGGER.info("Rejected client certificates directory: %s", config.certificates.rejected_clients_dir)
    LOGGER.info("Server certificate path: %s", config.certificates.server_certificate)

    async with server:
        await shutdown_event.wait()

    LOGGER.info("OPC UA server stopped")


async def validate_configuration(config: AppConfig) -> None:
    await build_server(config)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a configurable asyncua OPC UA server.")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to the YAML configuration file. Defaults to ./config.yaml",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate the YAML file, certificate paths, and node definitions without starting the server.",
    )
    args = parser.parse_args(argv)

    try:
        config = load_app_config(Path(args.config))
        configure_logging(config.logging_level, config.asyncua_logging_level)
        if args.check_config:
            asyncio.run(validate_configuration(config))
            LOGGER.info("Configuration is valid: %s", config.source_path)
            return 0

        asyncio.run(run_server(config))
        return 0
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0


def configure_logging(level_name: str, asyncua_level_name: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level_name),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("asyncua").setLevel(getattr(logging, asyncua_level_name))


async def _add_configured_node(parent, namespace_index: int, node: NodeConfig, path_segments: tuple[str, ...]):
    current_path = path_segments + (node.browse_name,)
    node_id = _resolve_node_id(namespace_index, node.node_id, current_path)

    if node.node_type == "folder":
        created_node = await parent.add_folder(node_id, node.browse_name)
        for child in node.children:
            await _add_configured_node(created_node, namespace_index, child, current_path)
        return created_node

    if node.node_type == "object":
        created_node = await parent.add_object(node_id, node.browse_name)
        for child in node.children:
            await _add_configured_node(created_node, namespace_index, child, current_path)
        return created_node

    variant_type = _resolve_variant_type(node.variant_type)
    value = _coerce_node_value(node.value, variant_type)
    created_node = await parent.add_variable(node_id, node.browse_name, value, varianttype=variant_type)
    if node.writable:
        await created_node.set_writable()
    return created_node


def _resolve_node_id(namespace_index: int, configured_node_id: str | int | None, path_segments: tuple[str, ...]):
    if configured_node_id is None:
        identifier = "/".join(_sanitize_node_id_segment(segment) for segment in path_segments)
        return ua.NodeId(identifier, namespace_index)
    if isinstance(configured_node_id, int):
        return ua.NodeId(configured_node_id, namespace_index)
    if configured_node_id.startswith(("ns=", "i=", "s=", "g=", "b=")):
        return ua.NodeId.from_string(configured_node_id)
    return ua.NodeId(configured_node_id, namespace_index)


def _sanitize_node_id_segment(segment: str) -> str:
    return "".join(character if character.isalnum() or character in {"-", "_", "."} else "_" for character in segment)


def _resolve_variant_type(variant_type_name: str | None) -> ua.VariantType | None:
    if variant_type_name is None:
        return None
    if not hasattr(ua.VariantType, variant_type_name):
        raise ConfigError(f"Unsupported variant_type: {variant_type_name}")
    return getattr(ua.VariantType, variant_type_name)


def _coerce_node_value(value, variant_type: ua.VariantType | None):
    if variant_type is None or value is None:
        return value

    if variant_type == ua.VariantType.DateTime and isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    return value


def _resolve_security_policies(policy_names: list[str]) -> list[ua.SecurityPolicyType]:
    resolved: list[ua.SecurityPolicyType] = []
    for name in policy_names:
        if name not in SECURITY_POLICY_MAP:
            supported = ", ".join(sorted(SECURITY_POLICY_MAP))
            raise ConfigError(f"Unsupported security policy '{name}'. Supported values: {supported}")
        resolved.append(SECURITY_POLICY_MAP[name])
    return resolved


def _private_key_password(config: AppConfig) -> str | bytes | None:
    env_var = config.certificates.private_key_password_env
    if not env_var:
        return None

    password = os.environ.get(env_var)
    if password is None:
        raise ConfigError(f"Environment variable '{env_var}' is not set.")
    return password.encode("utf-8")


def _validate_server_certificate_files(config: AppConfig) -> None:
    if not config.certificates.server_certificate.exists():
        raise FileNotFoundError(
            "Server certificate not found at "
            f"{config.certificates.server_certificate}. Put the server certificate inside "
            f"{config.certificates.server_dir} or update certificates.server_certificate in {config.source_path}."
        )
    if not config.certificates.server_private_key.exists():
        raise FileNotFoundError(
            "Server private key not found at "
            f"{config.certificates.server_private_key}. Put the server key inside "
            f"{config.certificates.server_dir} or update certificates.server_private_key in {config.source_path}."
        )


def _install_signal_handlers(shutdown_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for handled_signal in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(handled_signal, shutdown_event.set)
        except NotImplementedError:
            break
